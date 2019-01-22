if 'test' not in __import__('sys').argv[0]:
    import gevent.monkey
    gevent.monkey.patch_all()

import os, logging, json
from couchdb import Server, Session, ServerError, ResourceConflict
from datetime import timedelta, datetime
from jsonpointer import JsonPointerException
from jsonpatch import JsonPatchConflict, make_patch, JsonPatch, AddOperation as _AddOperation
try:
    from collections.abc import MutableMapping, MutableSequence
except ImportError:
    from collections import MutableMapping, MutableSequence
from pytz import timezone
#from gevent import spawn, wait
from gevent import sleep

try:
    from systemd.journal import JournalHandler
except ImportError:  # pragma: no cover
    JournalHandler = False

FORMAT = '%(asctime)-15s %(tenderid)s@%(rev)s %(message)s'
logging.basicConfig(level=logging.DEBUG, format=FORMAT)
LOGGER = logging.getLogger(__name__)
IGNORE = ['_attachments', '_revisions', 'revisions', 'dateModified', '_id', '_rev', 'doc_type']
TZ = timezone(os.environ['TZ'] if 'TZ' in os.environ else 'Europe/Kiev')


def get_now():
    return datetime.now(TZ)


def get_revision_changes(dst, src):
    return make_patch(dst, src).patch


def update_journal_handler_params(params):
    if not JournalHandler:
        return
    for i in LOGGER.handlers:
        if isinstance(i, JournalHandler):
            for x, j in params.items():
                i._extra[x.upper()] = j


class AddOperation(_AddOperation):
    """Adds an object property or an array element."""

    def apply(self, obj):
        try:
            value = self.operation["value"]
        except KeyError as ex:
            raise InvalidJsonPatch(
                "The operation does not contain a 'value' member")

        subobj, part = self.pointer.to_last(obj)

        if isinstance(subobj, MutableSequence):
            if part == '-':
                subobj.append(value)  # pylint: disable=E1103

            elif part > len(subobj) or part < 0:
                raise JsonPatchConflict("can't insert outside of list")

            else:
                subobj.insert(part, value)  # pylint: disable=E1103

        elif isinstance(subobj, MutableMapping):
            if part is None:
                obj = value  # we're replacing the root
            else:
                if part in subobj:
                    #this is the case when element was added in 2 versions of the document separetely
                    #see https://jira.prozorro.org/browse/CS-111
                    if isinstance(subobj[part], MutableSequence) and isinstance(value, MutableSequence):
                        #merge two arrays together
                        subobj[part] += value
                    else:
                        subobj[part] = value
                else:
                    subobj[part] = value

        else:
            raise TypeError("invalid document type {0}".format(type(subobj)))

        return obj

def _apply_patch(doc, patch, in_place=False):
    if isinstance(patch, basestring):
        patch = JsonPatch.from_string(patch)
    else:
        patch = JsonPatch(patch)
    # redefine Add operation to fix issue #CS-111
    patch.operations['add'] = AddOperation
    return patch.apply(doc, in_place)

def conflicts_resolve(db, c, dump_dir=None):
    """ Conflict resolution algorithm """
    changed = False
    ctender = c[u'doc']
    tid = c[u'id']
    trev = ctender[u'_rev']
    conflicts = ctender[u'_conflicts']
    if dump_dir:
        with open('{}@{}_conflicts.json'.format(os.path.join(dump_dir, tid), trev), 'w') as f:
            json.dump(ctender, f)
    update_journal_handler_params({
        'TENDER_ID': tid,
        'TENDERID': ctender.get(u'tenderID', ''),
        'TENDER_REV': trev,
        'RESULT': trev,
        'PARAMS': ','.join(conflicts),
    })
    LOGGER.info("Conflict detected", extra={'tenderid': tid, 'rev': trev, 'MESSAGE_ID': 'conflict_detected'})
    if 'revisions' in ctender:
        open_revs = dict([(i, None) for i in conflicts])
        open_revs[trev] = [(i.get('rev'), i['date']) for i in ctender['revisions']]
        td = {trev: ctender}
        for r in conflicts:
            try:
                t = db.get(tid, rev=r)
            except ServerError:
                update_journal_handler_params({'PARAMS': r})
                LOGGER.error("ServerError on getting revision", extra={'tenderid': tid, 'rev': r, 'MESSAGE_ID': 'conflict_error_get'})
                return
            if dump_dir:
                with open('{}@{}.json'.format(os.path.join(dump_dir, tid), r), 'w') as f:
                    json.dump(t, f)
            open_revs[r] = [(i.get('rev'), i['date']) for i in t['revisions']]
            if r not in td:
                td[r] = t.copy()
        common_chain = [i[0] for i in zip(*open_revs.values()) if all(map(lambda x: i[0]==x, i))]
        try:
            common_rev = common_chain[-1][0]
        except IndexError:
            LOGGER.error("Can't find common revision", extra={'tenderid': tid, 'rev': trev, 'MESSAGE_ID': 'conflict_error_common'})
            return
        common_index = len(common_chain)
        applied = [rev['date'] for rev in ctender['revisions'][common_index:]]
        for r in conflicts:
            tt = []
            t = td[r]
            revs = t['revisions']
            for rev in revs[common_index:][::-1]:
                if 'changes' not in rev:
                    continue
                tn = t.copy()
                try:
                    t = _apply_patch(t, rev['changes'])
                except JsonPatchConflict:
                    LOGGER.error("Can't restore revision", extra={'tenderid': tid, 'rev': trev, 'MESSAGE_ID': 'conflict_error_restore'})
                    return
                ti = dict([x for x in t.items() if x[0] not in IGNORE])
                tj = dict([x for x in tn.items() if x[0] not in IGNORE])
                tt.append((rev['date'], rev, get_revision_changes(ti, tj)))
            for i in tt[::-1]:
                if i[0] in applied:
                    continue
                t = ctender.copy()
                try:
                    ctender = _apply_patch(t, i[2])
                except JsonPointerException:
                    LOGGER.error("Can't apply patch", extra={'tenderid': tid, 'rev': trev, 'MESSAGE_ID': 'conflict_error_pointer'})
                    return
                except JsonPatchConflict:
                    LOGGER.error("Can't apply patch", extra={'tenderid': tid, 'rev': trev, 'MESSAGE_ID': 'conflict_error_patch'})
                    return
                patch = get_revision_changes(ctender, t)
                if patch:
                    revision = i[1]
                    revision['changes'] = patch
                    revision['rev'] = common_rev
                    ctender['revisions'].append(revision)
                applied.append(i[0])
                changed = True
    if changed:
        ctender['dateModified'] = get_now().isoformat()
        try:
            tid, trev = db.save(ctender)
        except ServerError:
            LOGGER.error("ServerError on saving resolution", extra={'tenderid': tid, 'rev': trev, 'MESSAGE_ID': 'conflict_error_save'})
            return
        except ResourceConflict:
            LOGGER.info("Conflict not resolved", extra={'tenderid': tid, 'rev': trev, 'MESSAGE_ID': 'conflict_not_resolved'})
            return
        else:
            update_journal_handler_params({'RESULT': trev})
            LOGGER.info("Conflict resolved", extra={'tenderid': tid, 'rev': trev, 'MESSAGE_ID': 'conflict_resolved'})
    else:
        LOGGER.info("Conflict resolved w/o changes", extra={'tenderid': tid, 'rev': trev, 'MESSAGE_ID': 'conflict_resolved_wo_changes'})
    uu=[]
    for r in conflicts:
        uu.append({'_id': tid, '_rev': r, '_deleted': True})
    try:
        results = db.update(uu)
    except ServerError:
        LOGGER.error("ServerError on deleting conflicts", extra={'tenderid': tid, 'rev': trev, 'MESSAGE_ID': 'conflict_error_deleting'})
        return
    else:
        update_journal_handler_params({'TENDER_REV': trev, 'RESULT': ','.join([str(x[0]) for x in results])})
        LOGGER.info("Deleting conflicts", extra={'tenderid': tid, 'rev': trev, 'MESSAGE_ID': 'conflict_deleting'})


def main(couchdb_url=None, couchdb_db='openprocurement', seq_file=None, dump_dir=None):
    if JournalHandler:
        params = {
            'TAGS': 'python,concord',
        }
        LOGGER.addHandler(JournalHandler(**params))
    if couchdb_url:
        server = Server(url=couchdb_url, session=Session(retry_delays=range(10)))
    else:
        server = Server(session=Session(retry_delays=range(10)))
    for i in range(10):
        try:
            db = server[couchdb_db]
        except:
            sleep(i)
        else:
            break
    else:
        db = server[couchdb_db]
    if dump_dir and not os.path.isdir(dump_dir):
        os.mkdir(dump_dir)
    if seq_file and os.path.isfile(seq_file):
        with open(seq_file) as f:
            fdata = f.read()
            last_seq = int(fdata) if fdata.isdigit() else 0
    else:
        last_seq = 0
    seq_block = last_seq / 100
    while True:
        cc = db.changes(timeout=55000, since=last_seq, feed='longpoll',
                        filter='_view', view='conflicts/all', include_docs=True,
                        conflicts=True)
        #wait([
            #spawn(conflicts_resolve, db, c, dump_dir)
            #for c in cc[u'results']
        #])
        for c in cc[u'results']:
            conflicts_resolve(db, c, dump_dir)
        last_seq = cc[u'last_seq']
        if seq_file and seq_block < last_seq / 100:
            with open(seq_file, 'w+') as f:
                f.write(str(last_seq))
            seq_block = last_seq / 100


if __name__ == "__main__":
    main()

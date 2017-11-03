# -*- coding: utf-8 -*-
import unittest
import random
from openprocurement.tender.belowthreshold.tests.base import test_organization
from openprocurement.concord.tests.base import BaseTenderWebTest
from openprocurement.concord.daemon import conflicts_resolve as resolve
# from json_tools import diff, patch as _patch

IGNORE = ['_attachments', '_revisions', 'revisions', 'dateModified', "_id", "_rev", "doc_type"]


def conflicts_resolve(db):
    """ Branch apply algorithm """
    for c in db.view('conflicts/all', include_docs=True, conflicts=True):
        resolve(db, c)


class TenderConflictsTest(BaseTenderWebTest):

    def patch_tender(self, i, j, app):
        for i in range(i, j):
            a = app(i)
            c = random.choice(['USD', 'UAH', 'RUB'])
            response = a.patch_json('/tenders/{}'.format(self.tender_id), {'data': {
                'title': "title changed #{}".format(i),
                'description': "description changed #{}".format(i),
                'value': {
                    'amount': i*1000 + 500,
                    'currency': c
                },
                'minimalStep': {
                    'currency': c
                }
            }})
            self.assertEqual(response.status, '200 OK')

    def test_conflict_draft(self):
        data = self.initial_data.copy()
        data['status'] = 'draft'
        response = self.app.post_json('/tenders', {'data': data})
        tender = response.json['data']
        self.assertEqual(tender['status'], 'draft')
        tender_id = tender['id']
        self.couchdb_server.replicate(self.db.name, self.db2.name)
        self.couchdb_server.replicate(self.db2.name, self.db.name)
        response = self.app.patch_json('/tenders/{}'.format(tender_id), {'data': {'status': 'active.enquiries'}})
        self.assertEqual(response.status, '200 OK')
        self.assertEqual(response.json['data']['status'], 'active.enquiries')
        response = self.app2.patch_json('/tenders/{}'.format(tender_id), {'data': {'status': 'active.enquiries'}})
        self.assertEqual(response.status, '200 OK')
        self.assertEqual(response.json['data']['status'], 'active.enquiries')
        self.couchdb_server.replicate(self.db.name, self.db2.name)
        self.couchdb_server.replicate(self.db2.name, self.db.name)
        self.assertGreater(len(self.db.view('conflicts/all')), 0)
        conflicts_resolve(self.db)
        self.assertEqual(len(self.db.view('conflicts/all')), 0)
        self.couchdb_server.replicate(self.db.name, self.db2.name)
        self.couchdb_server.replicate(self.db2.name, self.db.name)
        self.assertEqual(len(self.db.view('conflicts/all')), 0)

    def test_conflict_tenderID(self):
        self.db2.save({'_id': 'tenderID'})
        self.couchdb_server.replicate(self.db.name, self.db2.name)
        self.couchdb_server.replicate(self.db2.name, self.db.name)
        self.assertGreater(len(self.db.view('conflicts/all')), 0)
        conflicts_resolve(self.db)
        self.assertEqual(len(self.db.view('conflicts/all')), 0)
        self.couchdb_server.replicate(self.db.name, self.db2.name)
        self.couchdb_server.replicate(self.db2.name, self.db.name)
        self.assertEqual(len(self.db.view('conflicts/all')), 0)

    def test_conflict_simple(self):
        self.couchdb_server.replicate(self.db.name, self.db2.name)
        self.couchdb_server.replicate(self.db2.name, self.db.name)
        response = self.app.get('/tenders/{}'.format(self.tender_id))
        self.assertEqual(response.status, '200 OK')
        tender = response.json['data']
        response = self.app2.get('/tenders/{}'.format(self.tender_id))
        self.assertEqual(response.status, '200 OK')
        tender2 = response.json['data']
        self.assertEqual(tender, tender2)
        self.patch_tender(0, 10, lambda i: [self.app, self.app2][i % 2])
        self.couchdb_server.replicate(self.db.name, self.db2.name)
        self.couchdb_server.replicate(self.db2.name, self.db.name)
        self.assertGreater(len(self.db.view('conflicts/all')), 0)
        conflicts_resolve(self.db)
        self.assertEqual(len(self.db.view('conflicts/all')), 0)
        self.couchdb_server.replicate(self.db.name, self.db2.name)
        self.couchdb_server.replicate(self.db2.name, self.db.name)
        self.assertEqual(len(self.db.view('conflicts/all')), 0)
        tender = self.db.get(self.tender_id)
        self.assertEqual(len(tender['revisions']), 11)

    def test_conflict_quick_balancing(self):
        self.couchdb_server.replicate(self.db.name, self.db2.name)
        self.couchdb_server.replicate(self.db2.name, self.db.name)
        self.set_status('active.tendering')

        response = self.app.get('/tenders/{}'.format(self.tender_id))
        self.assertEqual(response.status, '200 OK')
        tender = response.json['data']

        response = self.app2.post_json('/tenders/{}/bids'.format(self.tender_id), {'data': {'tenderers': [test_organization], "value": {"amount": 401}}}, status=403)
        self.assertEqual(response.status, '403 Forbidden')
        self.assertEqual(response.content_type, 'application/json')
        self.assertEqual(response.json['errors'][0]["description"], "Can't add bid in current (active.enquiries) tender status")

        self.couchdb_server.replicate(self.db.name, self.db2.name)
        self.couchdb_server.replicate(self.db2.name, self.db.name)

        response = self.app2.post_json('/tenders/{}/bids'.format(self.tender_id), {'data': {'tenderers': [test_organization], "value": {"amount": 401}}})
        self.assertEqual(response.status, '201 Created')
        bid_id = response.json['data']['id']

        self.couchdb_server.replicate(self.db.name, self.db2.name)
        self.couchdb_server.replicate(self.db2.name, self.db.name)
        self.assertEqual(len(self.db.view('conflicts/all')), 0)
        tender = self.db.get(self.tender_id)
        self.assertEqual(len(tender['bids']), 1)
        self.assertEqual(tender['bids'][0]["id"], bid_id)
        self.assertEqual(tender['bids'][0]["value"]["amount"], 401)

    @unittest.skip("wait for bids")
    def test_conflict_insdel12(self):
        response = self.app.get('/tenders/{}'.format(self.tender_id))
        self.assertEqual(response.status, '200 OK')
        tender = response.json['data']
        self.set_status('active.tendering')
        response = self.app.post_json('/tenders/{}/bids'.format(self.tender_id), {'data': {'tenderers': [test_organization], "value": {"amount": 401}}})
        self.assertEqual(response.status, '201 Created')
        bid_id_to_del = response.json['data']['id']
        self.couchdb_server.replicate(self.db.name, self.db2.name)
        self.couchdb_server.replicate(self.db2.name, self.db.name)

        response = self.app.delete('/tenders/{}/bids/{}'.format(self.tender_id, bid_id_to_del))
        self.assertEqual(response.status, '200 OK')

        response = self.app2.post_json('/tenders/{}/bids'.format(self.tender_id), {'data': {'tenderers': [test_organization], "value": {"amount": 402}}})
        self.assertEqual(response.status, '201 Created')
        bid_id = response.json['data']['id']

        self.couchdb_server.replicate(self.db.name, self.db2.name)
        self.couchdb_server.replicate(self.db2.name, self.db.name)
        self.assertGreater(len(self.db.view('conflicts/all')), 0)
        conflicts_resolve(self.db)
        self.assertEqual(len(self.db.view('conflicts/all')), 0)
        self.couchdb_server.replicate(self.db.name, self.db2.name)
        self.couchdb_server.replicate(self.db2.name, self.db.name)
        self.assertEqual(len(self.db.view('conflicts/all')), 0)
        tender = self.db.get(self.tender_id)
        self.assertEqual(len(tender['bids']), 1)
        self.assertEqual(tender['bids'][0]["id"], bid_id)
        self.assertEqual(tender['bids'][0]["value"]["amount"], 402)

    @unittest.skip("wait for bids")
    def test_conflict_insdel21(self):
        response = self.app.get('/tenders/{}'.format(self.tender_id))
        self.assertEqual(response.status, '200 OK')
        tender = response.json['data']
        self.set_status('active.tendering')
        response = self.app.post_json('/tenders/{}/bids'.format(self.tender_id), {'data': {'tenderers': [test_organization], "value": {"amount": 401}}})
        self.assertEqual(response.status, '201 Created')
        bid_id_to_del = response.json['data']['id']
        self.couchdb_server.replicate(self.db.name, self.db2.name)
        self.couchdb_server.replicate(self.db2.name, self.db.name)

        response = self.app.post_json('/tenders/{}/bids'.format(self.tender_id), {'data': {'tenderers': [test_organization], "value": {"amount": 402}}})
        self.assertEqual(response.status, '201 Created')
        bid_id = response.json['data']['id']

        response = self.app2.delete('/tenders/{}/bids/{}'.format(self.tender_id, bid_id_to_del))
        self.assertEqual(response.status, '200 OK')

        self.couchdb_server.replicate(self.db.name, self.db2.name)
        self.couchdb_server.replicate(self.db2.name, self.db.name)
        self.assertGreater(len(self.db.view('conflicts/all')), 0)
        conflicts_resolve(self.db)
        self.assertEqual(len(self.db.view('conflicts/all')), 0)
        self.couchdb_server.replicate(self.db.name, self.db2.name)
        self.couchdb_server.replicate(self.db2.name, self.db.name)
        self.assertEqual(len(self.db.view('conflicts/all')), 0)
        tender = self.db.get(self.tender_id)
        self.assertEqual(len(tender['bids']), 1)
        self.assertEqual(tender['bids'][0]["id"], bid_id)
        self.assertEqual(tender['bids'][0]["value"]["amount"], 402)

    def test_conflict_insdel211(self):
        self.set_status('active.tendering')
        self.couchdb_server.replicate(self.db.name, self.db2.name)
        self.couchdb_server.replicate(self.db2.name, self.db.name)
        response = self.app.get('/tenders/{}'.format(self.tender_id))
        self.assertEqual(response.status, '200 OK')
        tender = response.json['data']

        response = self.app2.post_json('/tenders/{}/bids'.format(self.tender_id), {'data': {'tenderers': [test_organization], "value": {"amount": 401}}})
        self.assertEqual(response.status, '201 Created')
        bid_id = response.json['data']['id']

        response = self.app.post_json('/tenders/{}/bids'.format(self.tender_id), {'data': {'tenderers': [test_organization], "value": {"amount": 402}}})
        self.assertEqual(response.status, '201 Created')
        response = self.app.delete('/tenders/{}/bids/{}'.format(self.tender_id, response.json['data']['id']))
        self.assertEqual(response.status, '200 OK')

        self.couchdb_server.replicate(self.db.name, self.db2.name)
        self.couchdb_server.replicate(self.db2.name, self.db.name)
        self.assertGreater(len(self.db.view('conflicts/all')), 0)
        conflicts_resolve(self.db)
        self.assertEqual(len(self.db.view('conflicts/all')), 0)
        self.couchdb_server.replicate(self.db.name, self.db2.name)
        self.couchdb_server.replicate(self.db2.name, self.db.name)
        self.assertEqual(len(self.db.view('conflicts/all')), 0)
        tender = self.db.get(self.tender_id)
        self.assertEqual(len(tender['bids']), 1)
        self.assertEqual(tender['bids'][0]["id"], bid_id)
        self.assertEqual(tender['bids'][0]["value"]["amount"], 401)

    def test_conflict_insdel121(self):
        self.set_status('active.tendering')
        self.couchdb_server.replicate(self.db.name, self.db2.name)
        self.couchdb_server.replicate(self.db2.name, self.db.name)
        response = self.app.get('/tenders/{}'.format(self.tender_id))
        self.assertEqual(response.status, '200 OK')
        tender = response.json['data']

        response = self.app.post_json('/tenders/{}/bids'.format(self.tender_id), {'data': {'tenderers': [test_organization], "value": {"amount": 402}}})
        self.assertEqual(response.status, '201 Created')
        bid_id_to_del = response.json['data']['id']

        response = self.app2.post_json('/tenders/{}/bids'.format(self.tender_id), {'data': {'tenderers': [test_organization], "value": {"amount": 401}}})
        self.assertEqual(response.status, '201 Created')
        bid_id = response.json['data']['id']

        response = self.app.delete('/tenders/{}/bids/{}'.format(self.tender_id, bid_id_to_del))
        self.assertEqual(response.status, '200 OK')

        self.couchdb_server.replicate(self.db.name, self.db2.name)
        self.couchdb_server.replicate(self.db2.name, self.db.name)
        self.assertGreater(len(self.db.view('conflicts/all')), 0)
        conflicts_resolve(self.db)
        self.assertEqual(len(self.db.view('conflicts/all')), 0)
        self.couchdb_server.replicate(self.db.name, self.db2.name)
        self.couchdb_server.replicate(self.db2.name, self.db.name)
        self.assertEqual(len(self.db.view('conflicts/all')), 0)
        tender = self.db.get(self.tender_id)
        self.assertEqual(len(tender['bids']), 1)
        self.assertEqual(tender['bids'][0]["id"], bid_id)
        self.assertEqual(tender['bids'][0]["value"]["amount"], 401)

    def test_conflict_insdel112(self):
        self.set_status('active.tendering')
        self.couchdb_server.replicate(self.db.name, self.db2.name)
        self.couchdb_server.replicate(self.db2.name, self.db.name)
        response = self.app.get('/tenders/{}'.format(self.tender_id))
        self.assertEqual(response.status, '200 OK')
        tender = response.json['data']

        response = self.app.post_json('/tenders/{}/bids'.format(self.tender_id), {'data': {'tenderers': [test_organization], "value": {"amount": 402}}})
        self.assertEqual(response.status, '201 Created')
        response = self.app.delete('/tenders/{}/bids/{}'.format(self.tender_id, response.json['data']['id']))
        self.assertEqual(response.status, '200 OK')

        response = self.app2.post_json('/tenders/{}/bids'.format(self.tender_id), {'data': {'tenderers': [test_organization], "value": {"amount": 401}}})
        self.assertEqual(response.status, '201 Created')
        bid_id = response.json['data']['id']

        self.couchdb_server.replicate(self.db.name, self.db2.name)
        self.couchdb_server.replicate(self.db2.name, self.db.name)
        self.assertGreater(len(self.db.view('conflicts/all')), 0)
        conflicts_resolve(self.db)
        self.assertEqual(len(self.db.view('conflicts/all')), 0)
        self.couchdb_server.replicate(self.db.name, self.db2.name)
        self.couchdb_server.replicate(self.db2.name, self.db.name)
        self.assertEqual(len(self.db.view('conflicts/all')), 0)
        tender = self.db.get(self.tender_id)
        self.assertEqual(len(tender['bids']), 1)
        self.assertEqual(tender['bids'][0]["id"], bid_id)
        self.assertEqual(tender['bids'][0]["value"]["amount"], 401)

    def test_conflict_complex(self):
        self.couchdb_server.replicate(self.db.name, self.db2.name)
        self.couchdb_server.replicate(self.db2.name, self.db.name)
        self.patch_tender(0, 5, lambda i: [self.app, self.app2][i % 2])
        self.couchdb_server.replicate(self.db.name, self.db2.name)
        self.couchdb_server.replicate(self.db2.name, self.db.name)
        self.assertGreater(len(self.db.view('conflicts/all')), 0)
        conflicts_resolve(self.db)
        self.assertEqual(len(self.db.view('conflicts/all')), 0)
        tender = self.db.get(self.tender_id)
        self.assertEqual(len(tender['revisions']), 6)
        self.assertGreater(len(self.db2.view('conflicts/all')), 0)
        self.patch_tender(5, 10, lambda i: self.app2)
        self.couchdb_server.replicate(self.db.name, self.db2.name)
        self.couchdb_server.replicate(self.db2.name, self.db.name)
        self.assertGreater(len(self.db.view('conflicts/all')), 0)
        conflicts_resolve(self.db)
        self.assertEqual(len(self.db.view('conflicts/all')), 0)
        self.couchdb_server.replicate(self.db.name, self.db2.name)
        self.couchdb_server.replicate(self.db2.name, self.db.name)
        self.assertEqual(len(self.db.view('conflicts/all')), 0)
        tender = self.db.get(self.tender_id)
        self.assertEqual(len(tender['revisions']), 11)

    def test_conflict_oneway(self):
        self.couchdb_server.replicate(self.db.name, self.db2.name)
        self.couchdb_server.replicate(self.db2.name, self.db.name)
        self.patch_tender(0, 5, lambda i: [self.app, self.app2][i % 2])
        self.assertEqual(len(self.db.view('conflicts/all')), 0)
        self.couchdb_server.replicate(self.db2.name, self.db.name)
        self.assertGreater(len(self.db.view('conflicts/all')), 0)
        conflicts_resolve(self.db)
        self.assertEqual(len(self.db.view('conflicts/all')), 0)
        tender = self.db.get(self.tender_id)
        self.assertEqual(len(tender['revisions']), 6)
        self.patch_tender(5, 10, lambda i: self.app2)
        self.couchdb_server.replicate(self.db2.name, self.db.name)
        self.assertGreater(len(self.db.view('conflicts/all')), 0)
        conflicts_resolve(self.db)
        self.assertEqual(len(self.db.view('conflicts/all')), 0)
        tender = self.db.get(self.tender_id)
        self.assertEqual(len(tender['revisions']), 11)
        self.patch_tender(10, 15, lambda i: self.app2)
        self.couchdb_server.replicate(self.db.name, self.db2.name)
        self.couchdb_server.replicate(self.db2.name, self.db.name)
        self.assertGreater(len(self.db.view('conflicts/all')), 0)
        conflicts_resolve(self.db)
        self.assertEqual(len(self.db.view('conflicts/all')), 0)
        self.couchdb_server.replicate(self.db.name, self.db2.name)
        self.couchdb_server.replicate(self.db2.name, self.db.name)
        self.assertEqual(len(self.db.view('conflicts/all')), 0)
        tender = self.db.get(self.tender_id)
        self.assertEqual(len(tender['revisions']), 16)

    def test_conflict_tworesolutions(self):
        self.couchdb_server.replicate(self.db.name, self.db2.name)
        self.couchdb_server.replicate(self.db2.name, self.db.name)
        self.patch_tender(0, 10, lambda i: [self.app, self.app2][i % 2])
        self.assertEqual(len(self.db.view('conflicts/all')), 0)
        self.couchdb_server.replicate(self.db.name, self.db2.name)
        self.couchdb_server.replicate(self.db2.name, self.db.name)
        self.assertGreater(len(self.db.view('conflicts/all')), 0)
        conflicts_resolve(self.db)
        self.assertEqual(len(self.db.view('conflicts/all')), 0)
        self.assertGreater(len(self.db2.view('conflicts/all')), 0)
        conflicts_resolve(self.db2)
        self.assertEqual(len(self.db2.view('conflicts/all')), 0)
        #
        self.couchdb_server.replicate(self.db.name, self.db2.name)
        self.couchdb_server.replicate(self.db2.name, self.db.name)
        self.assertGreater(len(self.db.view('conflicts/all')), 0)
        conflicts_resolve(self.db)
        self.assertEqual(len(self.db.view('conflicts/all')), 0)
        #
        self.couchdb_server.replicate(self.db.name, self.db2.name)
        self.couchdb_server.replicate(self.db2.name, self.db.name)
        self.assertEqual(len(self.db.view('conflicts/all')), 0)
        tender = self.db.get(self.tender_id)
        self.assertEqual(len(tender['revisions']), 11)


def suite():
    suite = unittest.TestSuite()
    suite.addTest(unittest.makeSuite(TenderConflictsTest))
    return suite


if __name__ == '__main__':
    unittest.main(defaultTest='suite')

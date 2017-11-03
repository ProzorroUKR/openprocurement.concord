# -*- coding: utf-8 -*-
import webtest
import os
from openprocurement.api.tests.base import PrefixedRequestClass
from openprocurement.tender.belowthreshold.tests.base import BaseTenderWebTest as APIBaseTenderWebTest


class BaseTenderWebTest(APIBaseTenderWebTest):

    def setUp(self):
        self.app = webtest.TestApp(
            "config:tests.ini", relative_to=os.path.dirname(__file__))
        self.app.RequestClass = PrefixedRequestClass
        self.app.authorization = ('Basic', ('token', ''))
        self.couchdb_server = self.app.app.registry.couchdb_server
        self.db = self.app.app.registry.db
        self.app2 = webtest.TestApp(
            "config:tests2.ini", relative_to=os.path.dirname(__file__))
        self.app2.RequestClass = PrefixedRequestClass
        self.app2.authorization = ('Basic', ('token', ''))
        self.db2 = self.app2.app.registry.db
        # Create tender
        response = self.app.post_json('/tenders', {'data': self.initial_data})
        tender = response.json['data']
        self.tender_id = tender['id']
        status = tender['status']
        if self.initial_bids:
            response = self.set_status('active.tendering')
            status = response.json['data']['status']
            bids = []
            for i in self.initial_bids:
                response = self.app.post_json('/tenders/{}/bids'.format(self.tender_id), {'data': i})
                self.assertEqual(response.status, '201 Created')
                bids.append(response.json['data'])
            self.initial_bids = bids
        if self.initial_status != status:
            self.initial_status
            self.set_status(self.initial_status)

    def tearDown(self):
        del self.db[self.tender_id]
        del self.couchdb_server[self.db.name]
        del self.couchdb_server[self.db2.name]

# -*- coding: utf-8 -*-
##############################################################################
#
#    OpenERP, Open Source Management Solution
#    Copyright (C) 2004-2009 Tiny SPRL (<http://tiny.be>).
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Affero General Public License as
#    published by the Free Software Foundation, either version 3 of the
#    License, or (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU Affero General Public License for more details.
#
#    You should have received a copy of the GNU Affero General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
##############################################################################

from datetime import datetime, timedelta
import time
import requests
import json

from openerp import models, fields, api
from openerp.tools import DEFAULT_SERVER_DATETIME_FORMAT
from openerp.exceptions import Warning

import logging
_logger = logging.getLogger(__name__)

def get_status_and_message(data):
    '''Parse the status and error message (if applicable) from a JSON dict.
    '''
    status = data['response_status']
    message = data['response_message']

    if status == 1:
        error_code = data['response_data']['error_code']
        error_message = data['response_data']['error_message']

        print data
        if not error_message:
            error_message = "NOCODE"

        message = "{0} {1} {2}".format(status, error_code, error_message)

    return (status, message)

def https_post(url, payload, params={}, ignore_status=False):
    '''Posts a data payload to Bill.com. It can optionally check for failed status.
    '''
    headers = {'content-type': 'application/x-www-form-urlencoded'}

    try:
        response = requests.post(url, params={}, data=payload, headers=headers)
    except Exception as e:
        error = ('Could not post to {0}: {1}'.format(url, e))
        _logger.error(error)
        
    if response.status_code not in [200]:
        message = "received HTTP {0}: {1} when sending to {2}: {3}".format(
                    response.status_code, response.text, url, payload
        )
        _logger.error(message)
     
    try:
        data = json.loads(response.text)
        status, message = get_status_and_message(data)
    except:
        message = 'sent {0} got badly formatted reponse: {1}'.format(payload, response.text)
        _logger.error(message)   
        
    if message and message != 'Success':
        _logger.error(message)
        return []
        
    return data['response_data']

def format_list(sort=[], filters=[], start=0, max=999):
    ''' Converts the list options into Bill.Com json string
    sort=[('createdTime', 'desc')]
    filters=[('invoiceDate', '<', date.today())]
    '''
    data = dict(
        start = start,
        max = max
    )

    if sort:
        data['sort'] = [
            dict(field=name, asc=(order=='asc'))
            for name, order in sort
        ]

    if filters:
        data['filters']  = [
            dict(field=field, op=op, value=value)
            for field, op, value in filters
        ]

    data = json.dumps(data)
    return data

def format_id(record_id):
    data = dict(
        id = record_id
    )
    data = json.dumps(data)
    return data

class BillDotCom(models.Model):
    _name = 'bill.com'
    
    def _get_config_data(self):
        "Get the active configuration details"
        config = self.env['bill.com.config'].search([('is_active', '=', True)])
        if not config:
            _logger.warn('Bill.Com API configuration error')
            return False
        
        data = {
            'devKey': config.appkey,
            'userName': config.email,
            'password': config.password,
            'orgId': config.org_id,
        }
        return data, config.url
    
    def _login(self):
        "Login to the Bill.Com server"
        data, api_url = self._get_config_data()
        
        api_url = api_url + '/Login.json'
        
        response = https_post(api_url, data)
        if response:
            return response['sessionId']
        return False
    
    def _get_data(self, url, session, key, options):
        data = {
            "sessionId": session,
            "devKey": key,
            "data": options
        }
        
        response = https_post(url, data)
        return response
    
    @api.one
    def tracklog(self, data):
        log_registry = self.env['log.registry']
        
        registry_line_vals={
            'mode' : data['mode'],   
            'bill_state': data['bill_state'],
            'source_id': data['source_id'],
            'destination': data['destination'],
            'source_amount': data['source_amount'],
            'dest_amount': data['dest_amount'],
            'partner': data['partner'],
            'invoice_date': data['invoice_date'],
            'journal_id': data['journal_id'],
            'invoice_id': data['invoice_id'],
            'process': data['process'],
            'paid_date': data['paid_date'],
            'description': data['description'],
            'billupdated_time': data['billupdated_time'],
            'unique_id': data['unique_id'],
            'ischanged': False,
            'created_at': time.strftime(DEFAULT_SERVER_DATETIME_FORMAT)
        }
        
        registry_vals={
            'external_id': data['external_id'],
            'external_id2': data['external_id2'],
            'mode' : data['mode'],   
            'bill_state': data['bill_state'],
            'partner': data['partner'],
            'invoice_date': data['invoice_date'],
            'process': data['process'],
            'paid_date': data['paid_date'],
            'created_at': time.strftime(DEFAULT_SERVER_DATETIME_FORMAT)
        }
        
        external_id = data['external_id']
        existing_log = log_registry.search([('external_id','=',external_id)], limit=1)
        
        if existing_log:
            print 'Existing log: %s' % data['external_id']
            for log_line in existing_log.log_line:
                if log_line.billupdated_time != data['billupdated_time']:
                    registry_line_vals.update({'ischanged': True})
                
            if not data.get('invoice_date', False):
                data['invoice_date'] = existing_log.invoice_date
                
            registry_vals.update({'log_line': [(0, 0, registry_line_vals)]})
            existing_log.write(registry_vals)
        else:
            print 'New log: %s' % data['external_id']
            registry_vals.update({'log_line': [(0, 0, registry_line_vals)]})
            log_registry.create(registry_vals)
        return
    
    @api.one
    def update_log(self, bill_id, bill_date, src_id, dest_id, state, mode, partner_id, credit, desc,
                     paid_date, journal_id, invoice_id, unique_id, updated):
        res = {}
        res['external_id'] = bill_id
        res['external_id2'] = None
        res['source_id'] = src_id
        res['destination'] = dest_id
        res['bill_state'] = state
        res['mode'] = mode
        res['partner'] = partner_id
        res['source_amount'] = credit
        res['dest_amount'] = 0
        res['description'] = desc
        res['invoice_date'] = bill_date
        res['process'] = 'Bill.com'
        res['paid_date'] = paid_date
        res['journal_id'] = journal_id
        res['invoice_id'] = invoice_id
        res['unique_id']= unique_id
        res['billupdated_time']= updated
        
        self.tracklog(res)
        return
    
    @api.one
    def process_bill(self):
        "Integrate Bill.Com Bills with Odoo"
        
        ctx = dict(self._context)
        company = self.env['res.company']
        partner = self.env['res.partner']
        account_account = self.env['account.account']
        account_journal = self.env['account.journal']
        account_invoice = self.env['account.invoice']
        account_move = self.env['account.move']
        account_move_line = self.env['account.move.line']
        account_voucher = self.env['account.voucher']
        account_period = self.env['account.period']
        account_anlytic = self.env['account.analytic.account']
        payment_ids = []
        
        sessionId = self._login()
        if not sessionId:
            return False
        
        data, api_url = self._get_config_data()
        
        today = datetime.today()
        if 'from_date' in ctx:
            from_date = ctx.get('from_date')
        else:
            from_date = (today - timedelta(days=1)).strftime("%Y-%m-%d")
        to_date = today.strftime("%Y-%m-%d")
        
        #Convert datetime to iso 8601 format (%Y-%m-%dT%H:%M:%S)
        from_date += 'T00:00:00.000+0000'
        to_date += 'T23:59:59.000+0000'
        
        bill_options =  format_list(filters=[('updatedTime', '>', from_date), ('updatedTime','<',to_date)], max=999)
        list_bill_url = api_url + '/List/Bill.json'
        bills = self._get_data(list_bill_url, sessionId, data['devKey'], bill_options)
        
        _logger.info('%s Bill(s) Found from Bill.Com', str(len(bills)))
        
        company_txo = company.search([('name','ilike','TVET Operating')], limit=1)
        purchase_journal = account_journal.search([('name','ilike','Purchase Journal'), ('company_id','=',company_txo.id)], limit=1)
        invoice_account = account_account.search([('name','ilike','Current Liability - Accounts Payable'), ('company_id','=',company_txo.id)], limit=1)
        invoice_line_account = account_account.search([('name','ilike','ICR - BillPay Clearing Account'), ('type','!=','consolidation'), ('company_id','=',company_txo.id)], limit=1)
        
        if not (company_txo and purchase_journal and invoice_account and invoice_line_account):
            raise Warning(_('Configuration error!\nSome accounts are missing to create the invoice, are you sure you have supplier invoice the accounts?'))
        
        bill_count = 1
        bill_total_count = len(bills)
        for bill in bills:
            print 'Bill Processing : %s/%s' % (str(bill_count), str(bill_total_count))
            bill_count += 1
            
            bill_id = bill['id']
            vendor_id = bill['vendorId']
            bill_active = bill['isActive']
            bill_updated = bill['updatedTime']
            
            bill_date = bill['invoiceDate']
            bill_due = bill['dueDate']
            bill_number = bill['invoiceNumber']
            
            bill_lines = bill['billLineItems']
            
            odoo_partner = partner.search([('bill_id_api','=', vendor_id)], limit=1)
            moves = account_move.search([('billcom_bill_id','=', bill_id)])
            invoice = account_invoice.search([('api_bill_id','=', bill_id)], limit=1)
            
            if odoo_partner:
                print 'Existing Partner: %s' % odoo_partner.name
                paid_by = odoo_partner.paid_by
                odoo_partner_name = odoo_partner.name
            else:
                vendor_options =  format_id(vendor_id)
                vendor_url = api_url + '/Crud/Read/Vendor.json'
                bill_partner = self._get_data(vendor_url, sessionId, data['devKey'], vendor_options)
                
                if bill_partner:
                    paid_by = 'echeck' if bill_partner['payBy'] == '0' else 'ach'
                    bill_partner_name = bill_partner['name']
                    print 'New Partner: %s' % bill_partner_name
                    
                    odoo_partner = partner.search([('name','=',bill_partner_name), ('supplier','=',True)], limit=1)
                    if odoo_partner:
                        odoo_partner.write({'bill_id_api': vendor_id, 'paid_by': paid_by})
                    else:
                        partner_vals = {
                            'name' : bill_partner_name,  
                            'email' : bill_partner['email'],
                            'phone' : bill_partner['phone'],
                            'acc_number' : bill_partner['accNumber'],
                            'paid_by' : paid_by,
                            'bill_id_api': bill_partner['id'],
                            'supplier': True,
                            'city': bill_partner['addressCity'],
                            'street': bill_partner['address1'],
                            'street2': bill_partner['address2'],
                            'zip': bill_partner['addressZip'],
                        }
                        odoo_partner = partner.create(partner_vals)
             
            amount_total = 0
            bill_locations = {}
            for bill_line in bill_lines:
                location_id = bill_line.get('locationId', False)
                amount = bill_line['amount']
                amount_total += amount
                if location_id in bill_locations:
                    bill_locations[location_id]['amount'] += amount
                    bill_locations[location_id]['lineItem'].append(bill_line)
                else:
                    company_location = company.search([('bill_locationId','=',location_id)], limit=1)
                    if not company_location:
                        continue
                    else:
                        bill_locations[location_id]= {}
                        bill_locations[location_id]['amount'] = 0
                        bill_locations[location_id]['lineItem']= []
                        
                        bill_locations[location_id]['date']= bill_date;
                        bill_locations[location_id]['date_due']= bill_due;
                        bill_locations[location_id]['api_bill_id']= bill_id
                        bill_locations[location_id]['updatedTime']= bill_updated
                        bill_locations[location_id]['partner_id']= odoo_partner.id
                        bill_locations[location_id]['amount'] += amount
                        bill_locations[location_id]['lineItem'].append(bill_line)
                           
            ctx['company_id'] = company_txo.id
            ctx['account_period_prefer_normal'] = True 
            period_id = account_period.with_context(ctx).find(bill_date)
            
            invoice_line_vals = {
                'name' : '/', 
                'partner_id' : odoo_partner.id,  
                'company_id': company_txo.id,
                'quantity': 1,
                'price_unit': amount_total,
                'product_id' : '',
                'account_id' : invoice_line_account.id,   
            }
            
            invoice_vals = {
                'period_id': period_id.id,
                'date_invoice' : bill_date,
                'date_due': bill_due,
                'journal_id' : purchase_journal.id, 
                'account_id' : invoice_account.id,   
                'api_bill_id' : bill_id,
                'is_billcom': True,
                'bill_updatetime': bill_updated,
                'invoice_line': [(0, 0, invoice_line_vals)]
            }
            
            if invoice:
                print 'Existing Invoice: %s' % invoice.number
                
                #    Checking reconciliation     #
                skip_invoice = False
#                 for move_line in moves.line_id:
#                     if move_line.credit > 0 and 'Reconciliation' in move_line.account_id.name:
#                         if move_line.reconcile_partial_id or move_line.reconcile_id:
#                             skip_invoice = False
                        
                if bill_updated == invoice.bill_updatetime or skip_invoice:
                    print 'Skipping the Invoice: %s' % invoice.number
                    continue
                
                invoice.is_billcom = False
                
                for move in moves:
                    if move.id != invoice.move_id.id:
                        move_line = account_move_line.search([('move_id','=',move.id), ('credit','>',0)], limit=1)
                        if move_line and bill_active == "2":
                            self.update_log(bill_id, bill_date, move_line.company_id.id, invoice.company_id.id, 'cancel',
                                             invoice.partner_id.paid_by, invoice.partner_id.id, move_line.credit, 'Cancel Invoice Bill.com',
                                             None, None, invoice.id, None, None)
                            
                vouchers = account_voucher.search([('api_bill_id','=',bill_id)])
                for voucher in vouchers:
                    voucher.cancel_voucher()
                    payment_ids.append(voucher.api_payment_id.id)
                
                if bill_active == "2":
                    invoice.signal_workflow('invoice_cancel')
                else:
                    invoice.signal_workflow('invoice_cancel')
                    invoice.action_cancel_draft()
                    invoice.invoice_line.unlink()
                    
                    invoice.write(invoice_vals)
                    invoice.signal_workflow('invoice_open')
                moves.unlink()
            else:
                invoice_vals.update({
                    'state':'draft',
                    'supplier_invoice_number': bill_number,
                    'type':'in_invoice',
                    'partner_id' : odoo_partner.id,  
                    'company_id': company_txo.id,
                    'origin': 'Bill.com',
                })
                
                print 'New Invoice: %s' % bill_number
                invoice = account_invoice.create(invoice_vals)
                invoice.signal_workflow('invoice_open')
                
            if bill_active == "2":
                continue
                    
            print 'In Bill Locations'
            for bill_location in bill_locations:
                line_items = bill_locations[bill_location]['lineItem']
                is_first = True
                analytic_lines = []
                analytic_move = {}
                line_count = 0
                for line_item in line_items:
                    line_count + 1
                    location_company = company.search([('bill_locationId','=',bill_location)], limit=1)
                    if not location_company:
                        raise Warning(_('Configuration error!\nCompany is not found for location %s') % (bill_location))
                    analytic_inv_journal = account_journal.search([('name','ilike','BillPay Clearing Journal') , ('company_id','=',location_company.id)], limit=1)
                    ctx['company_id'] = location_company.id
                    ctx['account_period_prefer_normal'] = True 
                    location_period_id = account_period.with_context(ctx).find(bill_date)
                    if location_period_id:
                        coa_account_id = False
                        coa_options =  format_id(line_item['chartOfAccountId'])
                        coa_url = api_url + '/Crud/Read/ChartOfAccount.json'
                        coa = self._get_data(coa_url, sessionId, data['devKey'], coa_options)
                        if coa:
                            coa_name = coa['name']
                            coa_account = account_account.search([('name','=',coa_name), ('company_id','=',location_company.id)], limit=1)
                            if coa_account:
                                coa_account_id = coa_account.id
                            else:
                                description = 'Account Mentioned in Bill.com is not found in Vetzip. Account Name: '+ coa_name
                                self.update_log(bill_id, bill_date, location_company.id, None, None, paid_by, odoo_partner.id, line_item['amount'], 
                                                 description, None, None, None, None, None)
                                _logger.warn('%s Account Not Found In vetzip.', coa_name)
                                continue
                            
                        analytic_account_id = False
                        department_id = line_item['departmentId']
                        if department_id:
                            dept_options =  format_id(department_id)
                            dept_url = api_url + '/Crud/Read/Department.json'
                            department = self._get_data(dept_url, sessionId, data['devKey'], dept_options)
                            if department:
                                department_name = department['name']
                                analytic_account = account_anlytic.search([('name','=',department_name), ('company_id','=',location_company.id)], limit=1)
                                if analytic_account:
                                    analytic_account_id = analytic_account.id
                                else:
                                    description = 'Account Mentioned in Bill.com is not found in Vetzip. Account Name: '+ department_name
                                    self.update_log(bill_id, bill_date, location_company.id, None, None, paid_by, odoo_partner.id, line_item['amount'], 
                                                     description, None, None, None, None, None)
                                    _logger.warn('%s Analytic Account Mentioned in Bill.com is not found in Vetzip.', department_name)
                                    continue
                        
                        if is_first:
                            move_sequence_id = analytic_inv_journal.sequence_id.id
                            move_name = self.env['ir.sequence'].next_by_id(move_sequence_id)

                            analytic_move = {
                                'name': move_name,
                                'date' : bill_date,
                                'ref': invoice.number,
                                'journal_id' : analytic_inv_journal.id,
                                'period_id': location_period_id.id,
                                'company_id': location_company.id,
                                'billcom_bill_id': bill_id
                            }
                            
                            debit_account = account_account.search([('name','ilike','BillPay Clearing') , ('company_id','=',location_company.id)], limit=1)
                            if debit_account:
                                debit_line = {
                                    'name' : '/',  
                                    'date' : bill_date,
                                    'account_id': debit_account.id,
                                    'journal_id' : analytic_inv_journal.id,
                                    'period_id': location_period_id.id,
                                    'credit': bill_locations[bill_location]['amount'],
                                    'partner_id' : odoo_partner.id  
                                }
                                analytic_lines.append((0, 0, debit_line))
                        
                        if coa_account_id:
                            credit_line = {
                                'name' : '/',  
                                'date' : bill_date,
                                'account_id': coa_account_id,
                                'analytic_account_id':analytic_account_id,
                                'journal_id' : analytic_inv_journal.id,
                                'period_id': location_period_id.id,
                                'debit': line_item['amount'],
                                'partner_id' : odoo_partner.id, 
                            }
                            analytic_lines.append((0, 0, credit_line))
                        
                        asset_name = line_item.get('description','/')              
                        asset_account = account_account.search([('name','ilike','FA%'), ('id','=',coa_account_id)], limit=1)
                        if asset_account:
                            asset_category = self.env['account.asset.category'].search([('account_asset_id','=',asset_account.id)], limit=1)
                            if asset_category:
                                asset_vals = {
                                    'name': asset_name,
                                    'category_id': asset_category.id,
                                    'purchase_date': bill_date,
                                    'company_id': location_company.id,
                                    'purchase_value': line_item['amount'],
                                    'prorata': asset_category.prorata,
                                    'method_number': asset_category.method_number,
                                    'method_period': asset_category.method_period,
                                    'partner_id': odoo_partner.id,
                                    'code': invoice.number
                                }
                                self.env['account.asset.asset'].create(asset_vals)
                                print 'Asset Creation: %s' % asset_name
                        
                        is_first = False
                
                analytic_move.update({'line_id': analytic_lines})
                analytic_move_id = account_move.create(analytic_move)
                print 'Move: %s' % analytic_move['name']
                
                self.update_log(bill_id, bill_date, location_company.id, company_txo.id, 'open', paid_by, odoo_partner.id, bill_locations[bill_location]['amount'],
                                 'Invoice in Bill.com', None, analytic_move_id.id, invoice.id, line_item['id'], line_item['updatedTime'])
                
        return payment_ids
                
                

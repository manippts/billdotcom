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

from openerp import models, fields, api

class BillDotComConfig(models.Model):
    _name = 'bill.com.config'
    
    name = fields.Char(required=True)
    appkey = fields.Char('Developer Key', required=True)
    email = fields.Char('Email', required=True)
    password = fields.Char('Password', required=True)
    org_name = fields.Char('Organisation Name', required=True)
    org_id = fields.Char('Oraganisation ID', required=True)
    url = fields.Char('API URL', required=True)
    is_active = fields.Boolean('Is Active')
    
    
    
    
    
    
    
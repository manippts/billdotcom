# -*- coding: utf-8 -*-
{
    'name': "Bill.Com APIs",

    'summary': """
        Bill.com integration with Odoo""",

    'description': """
        The module integrates Odoo with the following features:
        - Bill
        - Invoice
        - Vendor
    """,

    'author': "iFenSys",
    'website': "http://www.ifensys.com",

    # Categories can be used to filter modules in modules listing
    # Check https://github.com/odoo/odoo/blob/master/openerp/addons/base/module/module_data.xml
    # for the full list
    'category': 'Tools',
    'version': '0.1',

    # any module necessary for this one to work correctly
    'depends': ['base'],

    # always loaded
    'data': [
        # 'security/ir.model.access.csv',
        'views/configuration_view.xml',
        'views/bill_view.xml'
    ],
    
    # only loaded in demonstration mode
#     'demo': [
#         'demo.xml',
#     ],
}
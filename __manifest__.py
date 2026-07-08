{
    'name': 'E-Tax Automatic Posting',
    'version': '18.0.1.0.0',
    'category': 'Accounting',
    'summary': 'Automatically post invoices and payments to the E-Tax API.',
    'description': """
        This module extends the account.move and account.payment models.
        When a customer invoice is confirmed or a payment is created, it automatically 
        posts the transactional data (with 10% VAT calculation) to the E-Tax REST API.
    """,
    'author': 'Expert Developer',
    'depends': ['account', 'etaxris'],
    'data': [
        'security/ir.model.access.csv',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'LGPL-3',
}

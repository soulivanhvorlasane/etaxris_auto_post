from odoo import fields, models

class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    etaxris_api_endpoint = fields.Char(
        string='E-Tax API Endpoint',
        config_parameter='etaxris_auto_post.api_endpoint',
        default='http://localhost:8069/api/etax/payment'
    )
    etaxris_api_token = fields.Char(
        string='E-Tax API Token',
        config_parameter='etaxris_auto_post.api_token',
        default='ac71b0212d793d832e7b1c742c007a88bc01d6ecce320a34324108a32d16b352'
    )

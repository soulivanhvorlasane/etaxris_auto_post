from odoo import fields, models

class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    etaxris_api_endpoint = fields.Char(
        string='E-Tax API Endpoint',
        config_parameter='etaxris_auto_post.api_endpoint',
        default='http://localhost:8069/api/etax/payment'
    )

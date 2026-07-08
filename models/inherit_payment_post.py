import requests
from odoo import models, api, _
from odoo.exceptions import UserError
import logging

_logger = logging.getLogger(__name__)

class AccountPayment(models.Model):
    _inherit = 'account.payment'

    def action_post(self):
        # 1. Call standard Odoo posting logic
        res = super(AccountPayment, self).action_post()

        # 2. After successful posting, push data to E-Tax API
        for payment in self:
            if payment.payment_type == 'inbound': # Only post incoming customer payments
                payment._post_payment_to_etaxris()
                
        return res

    def _post_payment_to_etaxris(self):
        self.ensure_one()
        
        buyer_tin = self.partner_id.vat or "Unknown TIN"
        invoice_no = getattr(self, 'memo', False) or getattr(self, 'payment_reference', False) or self.name or "Unknown Invoice"
        payment_date = self.date
        
        # Calculate 10% VAT
        sales_amount = float(self.amount)
        vat_amount = sales_amount * 0.10
        payment_method = self.payment_method_id.name or "payment"

        buyer_name = self.partner_id.name or "Unknown Customer"

        payload = {
            'buyer_tin': buyer_tin,
            'buyer_name': buyer_name,
            'invoice_no': invoice_no,
            'payment_date': str(payment_date),
            'sales_amount': sales_amount,
            'payment_method': payment_method
        }

        # Get API endpoint from settings
        payment_url = self.env['ir.config_parameter'].sudo().get_param(
            'etaxris_auto_post.api_endpoint', 
            default='http://localhost:8069/api/etax/payment'
        )
        
        # Use the static token from the current user's settings instead of the global configuration
        token = self.env.user.etax_api_token

        if not token:
            error_msg = _("E-Tax API Error: No Static Token found for your user. Please generate one in your User Preferences under the E-Tax API tab.")
            _logger.error(error_msg)
            self.message_post(body=error_msg)
            return False
        
        # Include token in payload as requested
        payload['token'] = token

        try:
            headers = {
                'Authorization': f'Bearer {token}',
                'Content-Type': 'application/json'
            }
            
            request_payload = {"params": payload}
            
            response = requests.post(payment_url, json=request_payload, headers=headers, timeout=5)
            data = response.json().get('result', {})
            
            if data.get('status') != 'success':
                error_msg = _("E-Tax API Error: %s") % str(data.get('message', 'Unknown error'))
                _logger.error(error_msg)
                self.message_post(body=error_msg)
                return False

            success_msg = _("Successfully posted payment for %s to E-Tax System.") % invoice_no
            self.message_post(body=success_msg)
            return True

        except requests.exceptions.RequestException as e:
            error_msg = _("E-Tax Network Error: %s") % str(e)
            _logger.error(error_msg)
            self.message_post(body=error_msg)
            return False

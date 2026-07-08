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
        
        buyer_tin = self.company_id.vat or "Unknown TIN"
        
        # Determine invoice number from payment reference
        ref_val = getattr(self, 'memo', False) or getattr(self, 'payment_reference', False) or self.name or ""
        invoice_no = ref_val if ref_val else "Unknown Invoice"
        
        # Try to find the actual invoice to get dynamic data like Untaxed Amount
        sales_amount = float(self.amount) # Fallback to payment amount
        invoice = self.env['account.move'].search([
            ('name', '=', invoice_no),
            ('move_type', '=', 'out_invoice')
        ], limit=1)
        
        if invoice:
            sales_amount = float(invoice.amount_untaxed)
            # The user explicitly wants TIN from Company info, so we ensure it remains company_id.vat
            buyer_tin = self.company_id.vat or invoice.company_id.vat or "Unknown TIN"
            
        payment_date = self.date
        
        # Map Odoo payment method to E-Tax API valid selections ('bank', 'cash', 'wallet')
        pm_name = (self.payment_method_id.name or '').lower()
        if 'cash' in pm_name:
            payment_method = 'cash'
        elif 'wallet' in pm_name or 'stripe' in pm_name or 'paypal' in pm_name:
            payment_method = 'wallet'
        else:
            payment_method = 'bank' # Default fallback

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

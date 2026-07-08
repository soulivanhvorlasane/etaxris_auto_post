import requests
from odoo import models, fields, _
from odoo.exceptions import UserError
import logging

_logger = logging.getLogger(__name__)

class AccountMove(models.Model):
    _inherit = 'account.move'

    def action_post(self):
        # 1. Call standard Odoo posting logic
        res = super(AccountMove, self).action_post()

        # 2. After successful posting, push data to E-Tax API
        notification = None
        for move in self:
            if move.move_type == 'out_invoice':
                success, msg = move._post_invoice_to_etaxris()
                if not notification:
                    notification = {
                        'type': 'ir.actions.client',
                        'tag': 'display_notification',
                        'params': {
                            'title': 'E-Tax Integration',
                            'message': msg,
                            'type': 'success' if success else 'danger',
                            'sticky': not success,
                        }
                    }
                
        if notification:
            return notification
        return res

    def _post_invoice_to_etaxris(self):
        """ Handles posting the invoice data to the local E-Tax REST API """
        self.ensure_one()

        buyer_tin = self.partner_id.vat or "Unknown TIN"
        buyer_name = self.partner_id.name or "Unknown Customer"
        invoice_no = self.name
        payment_date = self.invoice_date or fields.Date.context_today(self)
        
        # Calculate 10% VAT
        sales_amount = float(self.amount_total)
        vat_amount = sales_amount * 0.10

        # Note: the API natively handles creating the invoice, but the API endpoint 
        # is /api/etax/payment for the combined payload.
        payload = {
            'buyer_tin': buyer_tin,
            'buyer_name': buyer_name,
            'invoice_no': invoice_no,
            'payment_date': str(payment_date),
            'sales_amount': sales_amount,
            'vat_amount': vat_amount,
            'payment_method': "invoice_confirmation"
        }

        # Get API credentials from settings, falling back to defaults if not set
        payment_url = self.env['ir.config_parameter'].sudo().get_param(
            'etaxris_auto_post.api_endpoint', 
            default='http://localhost:8069/api/etax/payment'
        )
        token = self.env['ir.config_parameter'].sudo().get_param(
            'etaxris_auto_post.api_token',
            default='ac71b0212d793d832e7b1c742c007a88bc01d6ecce320a34324108a32d16b352'
        )
        
        # Following requirements: including token in payload AND header
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
                return False, error_msg

            success_msg = _("Successfully posted invoice %s to E-Tax System.") % invoice_no
            self.message_post(body=success_msg)
            return True, success_msg

        except requests.exceptions.RequestException as e:
            error_msg = _("E-Tax Network Error: %s") % str(e)
            _logger.error(error_msg)
            self.message_post(body=error_msg)
            return False, error_msg

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
        api_success = True
        api_called = False
        for payment in self:
            if payment.payment_type == 'inbound': # Only post incoming customer payments
                if not payment._post_payment_to_etaxris():
                    api_success = False
                api_called = True
                
        if api_called and isinstance(res, (bool, type(None))):
            if api_success:
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('E-Tax Auto Post Successful'),
                        'message': _('The payment was successfully posted to the E-Tax API.'),
                        'type': 'success',
                        'sticky': False,
                    }
                }
            else:
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('E-Tax Auto Post Failed'),
                        'message': _('Failed to post payment to the E-Tax API. Check the payment chatter for details.'),
                        'type': 'danger',
                        'sticky': True,
                    }
                }
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

class AccountPaymentRegister(models.TransientModel):
    _inherit = 'account.payment.register'

    def action_create_payments(self):
        # The standard method creates and posts the payments
        # This will internally trigger account.payment.action_post() which calls our E-Tax logic
        res = super(AccountPaymentRegister, self).action_create_payments()
        
        # If it's a customer payment (inbound), we need to determine if it succeeded
        # Since the payments are already created, we can check if they have E-Tax API Error messages in their chatter
        if self.payment_type == 'inbound':
            # Find the payments created in the current transaction for this wizard
            payments = self.env['account.payment'].search([('ref', '=', self.communication)])
            if not payments:
                # Fallback to order/invoice name
                payments = self.env['account.payment'].search([], order='id desc', limit=1)
            
            # Check if an error was logged on the payment
            api_failed = False
            for payment in payments:
                errors = self.env['mail.message'].search([
                    ('res_id', '=', payment.id),
                    ('model', '=', 'account.payment'),
                    ('body', 'ilike', 'E-Tax API Error')
                ], limit=1)
                if errors:
                    api_failed = True
                    
            if not api_failed:
                notification = {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('E-Tax Auto Post Successful'),
                        'message': _('The payment was successfully posted to the E-Tax API.'),
                        'type': 'success',
                        'sticky': False,
                        'next': res if isinstance(res, dict) else {'type': 'ir.actions.act_window_close'}
                    }
                }
            else:
                notification = {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('E-Tax Auto Post Failed'),
                        'message': _('Failed to post payment to the E-Tax API. Please check the chatter on the Payment record for error details.'),
                        'type': 'danger',
                        'sticky': True,
                        'next': res if isinstance(res, dict) else {'type': 'ir.actions.act_window_close'}
                    }
                }
            return notification
            
        return res

# Skill: Inheriting Payment Post and Triggering API Calls

This guide documents the exact step-by-step approach used in the `etaxris_auto_post` module to seamlessly integrate Odoo's payment confirmation with an external REST API (E-Tax). 

This pattern is highly reusable for any Odoo integration that needs to push data to an external service exactly when a payment is marked as "Paid".

## Step 1: Hooking into `action_post` of `account.payment`
Odoo triggers `action_post()` when a payment is confirmed. By inheriting `account.payment` and overriding this method, we guarantee that the API is only called *after* Odoo has successfully validated and posted the payment.

```python
class AccountPayment(models.Model):
    _inherit = 'account.payment'

    def action_post(self):
        # 1. Call standard Odoo posting logic
        res = super(AccountPayment, self).action_post()

        # 2. After successful posting, push data to the external API
        for payment in self:
            if payment.payment_type == 'inbound': # Only post customer payments
                payment._post_payment_to_etaxris()
                
        return res
```

## Step 2: Extracting Dynamic Data from the Related Invoice
Payments often only hold the total paid amount. To send accurate data (like the base untaxed amount or the company's Tax ID), we must extract the related invoice. We do this by searching `account.move` using the payment's reference (`memo` or `payment_reference`).

```python
    def _post_payment_to_etaxris(self):
        self.ensure_one()
        
        # Determine invoice number from payment reference safely
        ref_val = getattr(self, 'memo', False) or getattr(self, 'payment_reference', False) or self.name or ""
        invoice_no = ref_val if ref_val else "Unknown Invoice"
        
        # Try to find the actual invoice to get dynamic data like Untaxed Amount
        sales_amount = float(self.amount) # Fallback
        buyer_tin = self.company_id.vat or "Unknown TIN"

        invoice = self.env['account.move'].search([
            ('name', '=', invoice_no),
            ('move_type', '=', 'out_invoice')
        ], limit=1)
        
        if invoice:
            sales_amount = float(invoice.amount_untaxed)
            buyer_tin = self.company_id.vat or invoice.company_id.vat or "Unknown TIN"
```

## Step 3: Safely Mapping Odoo Fields to API Fields
Odoo's `payment_method_id.name` can be unpredictable (e.g., "Manual", "Stripe"). External APIs often expect strict selection values (e.g., "bank", "cash"). A robust mapping prevents crashes.

```python
        # Map Odoo payment method to API valid selections
        pm_name = (self.payment_method_id.name or '').lower()
        if 'cash' in pm_name:
            payment_method = 'cash'
        elif 'wallet' in pm_name or 'stripe' in pm_name or 'paypal' in pm_name:
            payment_method = 'wallet'
        else:
            payment_method = 'bank' # Default fallback
```

## Step 4: Fetching User-Specific Static Tokens
Instead of global configurations, we fetch the Static Token directly from the user executing the payment (`self.env.user`).

```python
        token = self.env.user.etax_api_token

        if not token:
            error_msg = _("API Error: No Static Token found for your user.")
            self.message_post(body=error_msg)
            return False
```

## Step 5: Showing a UI Notification in the Register Payment Wizard
Payments are usually created via the "Register Payment" wizard (`account.payment.register`). To show a green success notification to the user after they click "Create Payment", we must inherit the wizard and inject a `display_notification` client action into its return dictionary.

```python
class AccountPaymentRegister(models.TransientModel):
    _inherit = 'account.payment.register'

    def action_create_payments(self):
        # The standard method creates and posts the payments
        res = super(AccountPaymentRegister, self).action_create_payments()
        
        if self.payment_type == 'inbound':
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
            return notification
            
        return res
```

### Key Takeaways
* **Always run super() first** to ensure Odoo's internal state is fully updated before calling external APIs.
* **Map dynamic data carefully** by querying related records (`account.move`) when standard context isn't enough.
* **Catch all `requests` exceptions** and use `message_post()` to alert users silently without breaking their workflow.

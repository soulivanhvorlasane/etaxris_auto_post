# E-Tax Auto Post - Integration Documentation

This document outlines the API integration, configuration, and underlying logic for the **E-Tax Automatic Posting (`etaxris_auto_post`)** Odoo module.

## 1. Overview
The **E-Tax Auto Post** module automates the submission of transaction data from Odoo directly to an external E-Tax API. It intercepts standard accounting workflows and pushes financial data whenever an incoming customer payment is confirmed.

## 2. Configuration & Settings

### Global Settings
To configure the main endpoint, open Odoo and navigate to the App menu:
**E-Tax Auto Post** -> **Configuration** -> **Settings**.
* **E-Tax API Endpoint**: The URL where the payload will be sent. 
  *(Default: `http://localhost:8069/api/etax/payment`)*

### User Authentication (Static Token)
Each user must have a valid API token to post data. This is configured in the User Preferences:
1. Go to **Settings -> Users & Companies -> Users** (or click your profile in the top right -> My Profile).
2. Open the **E-Tax API** tab.
3. If the **Static Token** is empty, click the **Generate New Token** button.
This token will be securely passed as a Bearer token whenever you confirm a payment.

## 3. Triggers & Workflows
The module automatically triggers API calls in the following scenario:

### Customer Payment Confirmation
When an **Incoming Payment** (`inbound`) is confirmed (via `action_post`), the system extracts the payment amount, the associated invoice reference, and sends the transaction details to the E-Tax API. This applies seamlessly whether the payment is created manually or via the "Register Payment" wizard on an Invoice.

---

## 4. API Request Details
The module communicates with the E-Tax API via a `POST` request.

### HTTP Headers
The following headers are automatically included in every request:
```http
Content-Type: application/json
Authorization: Bearer <Your User Static Token>
```

### JSON Payload Structure
Odoo encapsulates the data inside a `params` object (Standard JSON-RPC style). The payload contains the following fields:

| Field Name | Type | Description | Source in Odoo |
|---|---|---|---|
| `buyer_tin` | String | Tax ID Number of the customer. | `partner_id.vat` |
| `buyer_name` | String | Name of the customer. | `partner_id.name` |
| `invoice_no` | String | The reference/invoice number. | `memo` or `payment_reference` |
| `payment_date` | String | Date of the transaction (YYYY-MM-DD). | `date` |
| `sales_amount` | Float | The total transaction amount. | `amount` |
| `payment_method`| String | Method of the transaction. | `payment_method_id.name` |
| `token` | String | The API token. | User Static Token |

#### Example Payload
```json
{
    "params": {
        "buyer_tin": "123456789",
        "buyer_name": "Acme Corp",
        "invoice_no": "INV/2026/00006",
        "payment_date": "2026-07-08",
        "sales_amount": 1000.0,
        "payment_method": "Manual",
        "token": "ac71b0212d793d832e7b1c742c007a88bc01d6ecce320a34324108a32d16b352"
    }
}
```

## 5. Response & Error Handling
The module expects a standard JSON response from the E-Tax API containing a `result` object with a `status` field.

### Success Response
If the API returns `"status": "success"`, Odoo logs a success message directly in the chatter (message thread) of the corresponding Payment record.
```json
{
    "result": {
        "status": "success",
        "message": "Records successfully created."
    }
}
```

### Error Response & Network Failures
If the API returns anything other than `"success"`, or if a network timeout/exception occurs:
1. The error details are written to the Odoo server log (`_logger.error`).
2. An error message is posted to the record's chatter, alerting the user that the synchronization failed.
3. If the user executing the payment lacks a Static Token, the system will instantly log an error in the chatter requesting them to generate one in their profile.

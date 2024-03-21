# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).
from odoo import models, api

class AccountMoveLine(models.Model):
    _inherit = "account.move.line"


    @api.onchange('product_id', 'tax_ids', 'price_unit','quantity')
    def onchange_product_id_perception(self):
        if self.move_id.partner_id and self.move_id.move_type in ('out_invoice', 'out_refund'):
            if self.move_id.partner_id.line_padron_type_ids and self.product_id:
                arba_line = self.move_id.partner_id.arba_alicuot_ids.filtered(
                    lambda x: x.to_date >= self.move_id.invoice_date
                    and x.from_date <= self.move_id.invoice_date
                    and x.company_id.id == self.move_id.company_id.id
                )
                if arba_line and self.price_subtotal >= 1:
                    amount = self.price_subtotal * arba_line.alicuota_percepcion / 100
                    minimum_perception = arba_line.padron_line_id.padron_type_id.minimum_calcule_perception
                    if amount >= minimum_perception:
                        padrons_type = arba_line.padron_line_id.import_padron_id.padron_type_id
                        tax_id = padrons_type.account_tax_perception_id
                        if tax_id and tax_id not in self.tax_ids:
                            self.tax_ids = [(4, tax_id.id)]
                    elif amount <= minimum_perception:
                        padrons_type = arba_line.padron_line_id.import_padron_id.padron_type_id
                        tax_id = padrons_type.account_tax_perception_id
                        if tax_id and tax_id.id in self.tax_ids.ids:
                            self.tax_ids = [(2, tax_id.id)]
    
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).
from odoo import models, api, _
from odoo.exceptions import ValidationError

class AccountMove(models.Model):
    _inherit = "account.move"

    def action_account_invoice_payment_group(self):
        self.ensure_one()
        if self.state != 'cancel':
            raise ValidationError(_(
                'You can only register payment if invoice is open'))
        return {
            'name': _('Register Payment'),
            'view_type': 'form',
            'view_mode': 'form',
            'res_model': 'account.payment.group',
            'view_id': False,
            'target': 'current',
            'type': 'ir.actions.act_window',
            'context': {
                # si bien el partner se puede adivinar desde los apuntes
                # con el default de payment group, preferimos mandar por aca
                # ya que puede ser un contacto y no el commercial partner (y
                # en los apuntes solo hay commercial partner)
                'default_account_invoice_id': self.id,
                'default_partner_id': self.partner_id.id,
                'to_pay_move_line_ids': self.open_move_line_ids.ids,
                'pop_up': True,
                'default_company_id': self.company_id.id,
            },
        }

    def control_perception(self):
        for self_obj in self:
            list_id_delete = []
            invoice_lines = []

            for padron_type_obj in self_obj.partner_id.line_padron_type_ids:
                for tax_obj in self_obj.line_ids:

                    # Get alicuot for date and padron.
                    corresponding_alicuota = self_obj.partner_id.get_current_alicuota(padron_type_obj, self_obj.invoice_date)

                    if not corresponding_alicuota:
                        continue

                    base_amount = self_obj.amount_untaxed
                    calculated_minimum = base_amount * corresponding_alicuota.alicuota_percepcion / 100

                    if base_amount < padron_type_obj.minimum_base_perception or calculated_minimum < padron_type_obj.minimum_calcule_perception:
                        list_id_delete.append(tax_obj.id)

                        for invoice_line_obj in self_obj.invoice_line_ids:
                            for line_tax_obj in invoice_line_obj.tax_ids:
                                if line_tax_obj.id == padron_type_obj.account_tax_perception_id.id:
                                    invoice_line_obj.tax_ids = [(3, line_tax_obj.id)]

            for lines in self_obj.invoice_line_ids:
                invoice_lines.append((0, 0, {
                    'product_id': lines.product_id.id,
                    'account_id': lines.account_id.id,
                    'quantity': lines.quantity,
                    'product_uom_id': lines.product_uom_id.id,
                    'price_unit': lines.price_unit,
                    'discount': lines.discount,
                    'tax_ids': [(6, 0, lines.tax_ids.ids)]
                }))

            self_obj.line_ids = [(5, 0, 0)]
            self_obj.invoice_line_ids = invoice_lines





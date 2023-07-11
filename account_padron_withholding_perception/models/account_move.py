# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).
from odoo import models, api, _
from odoo.exceptions import ValidationError


class AccountMove(models.Model):
    _inherit = "account.move"

    def _prepare_invoice_line_from_po_line(self, line):
        result = super(AccountMove, self)._prepare_invoice_line_from_po_line(line)
        list_add =  []
        for line_obj in self.partner_id.line_padron_type_ids:
            list_add.append(line_obj.id)
        result['ret_perc_type_ids'] = list_add
        return result

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

    def set_retention_all(self):
        list_add =  []
        for rec in self:
            for line_obj in rec.partner_id.line_padron_type_ids:
                list_add.append(line_obj.id)
            for invoice_line_obj in rec.invoice_line_ids:
                invoice_line_obj.ret_perc_type_ids = list_add

    def control_perception(self):
        for self_obj in self:
            list_id_delete = []
            invoice_lines = []
            for tax_obj in self_obj.line_ids:
                for padron_type_obj in self_obj.partner_id.line_padron_type_ids:
                    if padron_type_obj.account_tax_perception_id.id == tax_obj.tax_line_id.id:
                        if tax_obj.tax_line_id.withholding_non_taxable_amount < padron_type_obj.minimum_base_perception or tax_obj.tax_line_id.amount < padron_type_obj.minimum_calcule_perception:
                            list_id_delete.append(tax_obj.id)
                            for invoice_line_obj in self_obj.invoice_line_ids:
                                for line_tax_obj in invoice_line_obj.tax_ids:
                                    if line_tax_obj.id == padron_type_obj.account_tax_perception_id.id:
                                        invoice_line_obj.tax_ids = [(3,  line_tax_obj.id )]
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
            self_obj.line_ids = [(5,0,0)]
            self_obj.invoice_line_ids = invoice_lines


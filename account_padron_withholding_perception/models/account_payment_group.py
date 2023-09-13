# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).
from odoo import models, _


class AccountPaymentGroup(models.Model):
    _inherit = "account.payment.group"

    def compute_withholdings(self):
        self.ensure_one()
        result = super(AccountPaymentGroup, self).compute_withholdings()

        domain = [
            ('partner_id', '=', self.partner_id.id),
            ('to_date', '>=', self.payment_date),
            ('from_date', '<=', self.payment_date),
            ('company_id', '=', self.company_id.id),
        ]
        arba_line = self.env['res.partner.arba_alicuot'].search(domain, limit=1)

        padron_type = arba_line.padron_line_id.padron_type_id.filtered(
            lambda x: x.company_id.id == self.company_id.id
        )

        retention_line = self.search_line_retention(padron_type.account_tax_retention_id)

        if retention_line.amount < padron_type.minimum_calcule_retention:
            display_msg = _(
                'The minimum calculated retention {} is higher than the amount {} '
                'in the payment, so it is not applied in this payment'
            ).format(padron_type.minimum_calcule_retention, retention_line.amount)
            retention_line.unlink()
            self.message_post(body=display_msg)
            return result

        if retention_line:
            total_to_discount = self.total_amount_retention(
                padron_type.minimum_base_retention, arba_line.alicuota_retencion
            )
            if total_to_discount >= retention_line.amount:
                display_msg = _(
                'The minimum base retention {} is higher than the untaxed amount '
                'in the invoice, so it is not applied in this payment'
                ).format(padron_type.minimum_base_retention)
                retention_line.unlink()
            else:
                display_msg = _(
                'The minimum base retention {} is higher than the untaxed amount '
                'on some of the invoice, so the following discunt {} is applied to '
                'withholding on the total in this payment.'
                ).format(padron_type.minimum_base_retention, total_to_discount)
                retention_line.amount -= total_to_discount

            self.message_post(body=display_msg)
        return result

    def search_line_retention(self, tax):
        retention_line = self.payment_ids.filtered(
            lambda x: x.tax_withholding_id.id == tax.id
        )
        return retention_line

    def total_amount_retention(self, base_minimum_retention, percent_retention_arba):
        total_to_discount = 0
        for move_line in self.to_pay_move_line_ids:
            if move_line.move_id.move_type in ["in_invoice", "in_refund"]:
                if base_minimum_retention > move_line.move_id.amount_untaxed:
                    total_to_discount += (
                        move_line.move_id.amount_untaxed * percent_retention_arba / 100
                    )

        return total_to_discount

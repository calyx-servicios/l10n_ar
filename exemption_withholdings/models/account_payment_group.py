from odoo import models, fields


class AccountPaymentGroup(models.Model):
    _inherit = 'account.payment.group'

    exempt_msj = fields.Html('Exemptions Information')

    def compute_withholdings(self):
        res = super(AccountPaymentGroup, self).compute_withholdings()

        matched = None
        if self.partner_id.exemption_withholding_ids:
            for exemption in self.partner_id.exemption_withholding_ids:
                if exemption.active_tax:
                    tax_ext = self.payment_ids.filtered(
                        lambda x: exemption.date_to.date() >= x.date and exemption.date_from.date() <= x.date and exemption.account_tax_id.id == x.tax_withholding_id.id
                    )
                    if not matched:
                        matched = tax_ext
                    else:
                        matched += tax_ext
        if matched:
            for match in matched:
                match.unlink()

        return res

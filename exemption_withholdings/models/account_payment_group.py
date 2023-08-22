from odoo import models, fields


class AccountPaymentGroup(models.Model):
    _inherit = 'account.payment.group'

    exempt_msj = fields.Html('Exemptions Information')

    def compute_withholdings(self):
        res = super(AccountPaymentGroup, self).compute_withholdings()

        matched = None
        if self.partner_id.exemption_withholding_ids:
            tax_applied = self.env['account.tax'].search([('company_id', '=', self.company_id), ('vat_iva_applied', '=', True)])
            for exemption in self.partner_id.exemption_withholding_ids:
                if exemption.active_tax:
                    tax_ext = self.payment_ids.filtered(
                        lambda x: exemption.date_to.date() >= x.date and exemption.date_from.date() <= x.date and exemption.account_tax_id.id == x.tax_withholding_id.id
                    )
                    if not matched:
                        matched = tax_ext
                    else:
                        matched += tax_ext
            if self.partner_id.l10n_ar_afip_responsibility_type_id.code == '6':

                tax_avoid = self.payment_ids.filtered(lambda x: x.tax_withholding_id.id == tax_applied.id)
                if not matched:
                    matched = tax_avoid
                else:
                    matched += tax_avoid

        if matched:
            for match in matched:
                match.unlink()

        return res

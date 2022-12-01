from odoo import models, _
from odoo.exceptions import UserError
import logging
import sys
import traceback
from datetime import datetime

_logger = logging.getLogger(__name__)

try:
    from pysimplesoap.client import SoapFault
except ImportError:
    _logger.debug("Can not `from pyafipws.soap import SoapFault`.")


class AccountMove(models.Model):
    _inherit = "account.move"

    def do_pyafipws_request_cae(self):
        "Request to AFIP the invoices' Authorization Electronic Code (CAE)"
        for inv in self:
            if inv.afip_auth_code:
                continue

            afip_ws = inv.journal_id.afip_ws
            if not afip_ws:
                continue

            if not afip_ws:
                raise UserError(
                    _(
                        "If you use electronic journals (invoice id %s) you need "
                        "configure AFIP WS on the journal"
                    )
                    % (inv.id)
                )

            if not inv.validation_type:
                msg = (
                    "Factura validada solo localmente por estar en ambiente "
                    "de homologación sin claves de homologación"
                )
                inv.write(
                    {
                        "afip_auth_mode": "CAE",
                        "afip_auth_code": "68448767638166",
                        "afip_auth_code_due": inv.invoice_date,
                        "afip_result": "",
                        "afip_message": msg,
                    }
                )
                inv.message_post(body=msg)
                continue

            commercial_partner = inv.commercial_partner_id
            country = commercial_partner.country_id
            journal = inv.journal_id
            pos_number = journal.l10n_ar_afip_pos_number
            doc_afip_code = inv.l10n_latam_document_type_id.code

            ws = inv.company_id.get_connection(afip_ws).connect()

            if afip_ws == "wsfex":
                if not country:
                    raise UserError(
                        _('For WS "%s" country is required on partner' % (afip_ws))
                    )
                elif not country.code:
                    raise UserError(
                        _(
                            'For WS "%s" country code is mandatory'
                            "Country: %s" % (afip_ws, country.name)
                        )
                    )
                elif not country.l10n_ar_afip_code:
                    raise UserError(
                        _(
                            'For WS "%s" country afip code is mandatory'
                            "Country: %s" % (afip_ws, country.name)
                        )
                    )

            ws_next_invoice_number = (
                int(
                    inv.journal_id.get_pyafipws_last_invoice(
                        inv.l10n_latam_document_type_id
                    )["result"]
                )
                + 1
            )

            partner_id_code = (
                commercial_partner.l10n_latam_identification_type_id.l10n_ar_afip_code
            )
            tipo_doc = partner_id_code or "99"
            nro_doc = partner_id_code and commercial_partner.vat or "0"
            cbt_desde = cbt_hasta = cbte_nro = ws_next_invoice_number
            concepto = tipo_expo = int(inv.l10n_ar_afip_concept)

            fecha_cbte = inv.invoice_date
            if afip_ws != "wsmtxca":
                fecha_cbte = inv.invoice_date.strftime("%Y%m%d")

            mipyme_fce = int(doc_afip_code) in [201, 206, 211]
            if (
                int(concepto) != 1
                and int(doc_afip_code) not in [202, 203, 207, 208, 212, 213]
                or mipyme_fce
            ):
                fecha_venc_pago = inv.invoice_date_due or inv.invoice_date
                if afip_ws != "wsmtxca":
                    fecha_venc_pago = fecha_venc_pago.strftime("%Y%m%d")
            else:
                fecha_venc_pago = None

            if int(concepto) != 1:
                fecha_serv_desde = inv.l10n_ar_afip_service_start
                fecha_serv_hasta = inv.l10n_ar_afip_service_end
                if afip_ws != "wsmtxca":
                    fecha_serv_desde = fecha_serv_desde.strftime("%Y%m%d")
                    fecha_serv_hasta = fecha_serv_hasta.strftime("%Y%m%d")
            else:
                fecha_serv_desde = fecha_serv_hasta = None

            amounts = self._l10n_ar_get_amounts()
            imp_total = str("%.2f" % inv.amount_total)
            imp_tot_conc = str("%.2f" % amounts["vat_untaxed_base_amount"])

            if inv.l10n_latam_document_type_id.l10n_ar_letter == "C":
                imp_neto = str("%.2f" % inv.amount_untaxed)
            else:
                imp_neto = str("%.2f" % amounts["vat_taxable_amount"])
            imp_iva = str("%.2f" % amounts["vat_amount"])

            imp_trib = str("%.2f" % amounts["not_vat_taxes_amount"])
            imp_op_ex = str("%.2f" % amounts["vat_exempt_base_amount"])
            moneda_id = inv.currency_id.l10n_ar_afip_code
            moneda_ctz = inv.l10n_ar_currency_rate

            CbteAsoc = inv.get_related_invoices_data()

            if afip_ws == "wsfe":
                ws.CrearFactura(
                    concepto,
                    tipo_doc,
                    nro_doc,
                    doc_afip_code,
                    pos_number,
                    cbt_desde,
                    cbt_hasta,
                    imp_total,
                    imp_tot_conc,
                    imp_neto,
                    imp_iva,
                    imp_trib,
                    imp_op_ex,
                    fecha_cbte,
                    fecha_venc_pago,
                    fecha_serv_desde,
                    fecha_serv_hasta,
                    moneda_id,
                    moneda_ctz,
                )

            elif afip_ws == "wsfex":

                if inv.invoice_incoterm_id:
                    incoterms = inv.invoice_incoterm_id.code
                    incoterms_ds = inv.invoice_incoterm_id.name

                    incoterms_ds = incoterms_ds and incoterms_ds[:20]
                else:
                    incoterms = incoterms_ds = None

                if int(doc_afip_code) == 19 and tipo_expo == 1:

                    permiso_existente = "N"
                else:
                    permiso_existente = ""
                obs_generales = inv.narration

                if inv.invoice_payment_term_id:
                    forma_pago = inv.invoice_payment_term_id.name
                    obs_comerciales = inv.invoice_payment_term_id.name
                else:
                    forma_pago = obs_comerciales = None

                fecha_pago = (
                    datetime.strftime(inv.invoice_date_due, "%Y%m%d")
                    if int(doc_afip_code) == 19
                    and tipo_expo in [2, 4]
                    and inv.invoice_date_due
                    else ""
                )

                idioma_cbte = 1

                nombre_cliente = commercial_partner.name
                if nro_doc:
                    id_impositivo = nro_doc
                    cuit_pais_cliente = None
                elif country.code != "AR" and nro_doc:
                    id_impositivo = None
                    if commercial_partner.is_company:
                        cuit_pais_cliente = country.cuit_juridica
                    else:
                        cuit_pais_cliente = country.cuit_fisica
                    if not cuit_pais_cliente:
                        raise UserError(
                            _(
                                "No vat defined for the partner and also no CUIT "
                                "set on country"
                            )
                        )

                domicilio_cliente = " - ".join(
                    [
                        commercial_partner.name or "",
                        commercial_partner.street or "",
                        commercial_partner.street2 or "",
                        commercial_partner.zip or "",
                        commercial_partner.city or "",
                    ]
                )
                pais_dst_cmp = commercial_partner.country_id.l10n_ar_afip_code
                ws.CrearFactura(
                    doc_afip_code,
                    pos_number,
                    cbte_nro,
                    fecha_cbte,
                    imp_total,
                    tipo_expo,
                    permiso_existente,
                    pais_dst_cmp,
                    nombre_cliente,
                    cuit_pais_cliente,
                    domicilio_cliente,
                    id_impositivo,
                    moneda_id,
                    moneda_ctz,
                    obs_comerciales,
                    obs_generales,
                    forma_pago,
                    incoterms,
                    idioma_cbte,
                    incoterms_ds,
                    fecha_pago,
                )
            elif afip_ws == "wsbfe":
                zona = 1
                impto_liq_rni = 0.0
                imp_iibb = amounts["iibb_perc_amount"]
                imp_perc_mun = amounts["mun_perc_amount"]
                imp_internos = (
                    amounts["intern_tax_amount"] + amounts["other_taxes_amount"]
                )
                imp_perc = (
                    amounts["vat_perc_amount"]
                    + amounts["profits_perc_amount"]
                    + amounts["other_perc_amount"]
                )

                ws.CrearFactura(
                    tipo_doc,
                    nro_doc,
                    zona,
                    doc_afip_code,
                    pos_number,
                    cbte_nro,
                    fecha_cbte,
                    imp_total,
                    imp_neto,
                    imp_iva,
                    imp_tot_conc,
                    impto_liq_rni,
                    imp_op_ex,
                    imp_perc,
                    imp_iibb,
                    imp_perc_mun,
                    imp_internos,
                    moneda_id,
                    moneda_ctz,
                    fecha_venc_pago,
                )

            if afip_ws in ["wsfe", "wsbfe"]:
                if mipyme_fce:

                    ws.AgregarOpcional(
                        opcional_id=2101, valor=inv.invoice_partner_bank_id.acc_number
                    )

                    transmission_type = (
                        self.env["ir.config_parameter"]
                        .sudo()
                        .get_param("l10n_ar_afipws_fe.fce_transmission", "")
                    )
                    if transmission_type:
                        ws.AgregarOpcional(opcional_id=27, valor=transmission_type)
                elif int(doc_afip_code) in [202, 203, 207, 208, 212, 213]:
                    valor = inv.afip_fce_es_anulacion and "S" or "N"
                    ws.AgregarOpcional(opcional_id=22, valor=valor)

            if afip_ws not in ["wsfex", "wsbfe"]:
                vat_taxable = self.env["account.move.line"]
                for line in self.line_ids:
                    if (
                        any(
                            tax.tax_group_id.l10n_ar_vat_afip_code
                            and tax.tax_group_id.l10n_ar_vat_afip_code
                            not in ["0", "1", "2"]
                            for tax in line.tax_line_id
                        )
                        and line.price_subtotal
                    ):
                        vat_taxable |= line
                for vat in vat_taxable:
                    ws.AgregarIva(
                        vat.tax_line_id.tax_group_id.l10n_ar_vat_afip_code,
                        "%.2f"
                        % sum(
                            self.invoice_line_ids.filtered(
                                lambda x: x.tax_ids.filtered(
                                    lambda y: y.tax_group_id.l10n_ar_vat_afip_code
                                    == vat.tax_line_id.tax_group_id.l10n_ar_vat_afip_code
                                )
                            ).mapped("price_subtotal")
                        ),
                        "%.2f" % vat.price_subtotal,
                    )

                not_vat_taxes = self.line_ids.filtered(
                    lambda x: x.tax_line_id
                    and x.tax_line_id.tax_group_id.l10n_ar_tribute_afip_code
                )
                for tax in not_vat_taxes:
                    ws.AgregarTributo(
                        tax.tax_line_id.tax_group_id.l10n_ar_tribute_afip_code,
                        tax.tax_line_id.tax_group_id.name,
                        "%.2f"
                        % sum(
                            self.invoice_line_ids.filtered(
                                lambda x: x.tax_ids.filtered(
                                    lambda y: y.tax_group_id.l10n_ar_tribute_afip_code
                                    == tax.tax_line_id.tax_group_id.l10n_ar_tribute_afip_code
                                )
                            ).mapped("price_subtotal")
                        ),
                        0,
                        "%.2f" % tax.price_subtotal,
                    )

            if CbteAsoc:
                doc_number_parts = self._l10n_ar_get_document_number_parts(
                    CbteAsoc.l10n_latam_document_number,
                    CbteAsoc.l10n_latam_document_type_id.code,
                )
                if afip_ws == "wsfex":
                    ws.AgregarCmpAsoc(
                        CbteAsoc.l10n_latam_document_type_id.code,
                        doc_number_parts["point_of_sale"],
                        doc_number_parts["invoice_number"],
                        self.company_id.vat,
                    )
                else:
                    ws.AgregarCmpAsoc(
                        CbteAsoc.l10n_latam_document_type_id.code,
                        doc_number_parts["point_of_sale"],
                        doc_number_parts["invoice_number"],
                        self.company_id.vat,
                        afip_ws != "wsmtxca"
                        and CbteAsoc.invoice_date.strftime("%Y%m%d")
                        or CbteAsoc.invoice_date.strftime("%Y-%m-%d"),
                    )

            if afip_ws != "wsfe":
                for line in inv.invoice_line_ids.filtered(lambda x: not x.display_type):
                    codigo = line.product_id.default_code
                    if not line.product_uom_id:
                        umed = "7"
                    elif not line.product_uom_id.l10n_ar_afip_code:
                        raise UserError(
                            _(
                                "Not afip code con producto UOM %s"
                                % (line.product_uom_id.name)
                            )
                        )
                    else:
                        umed = line.product_uom_id.l10n_ar_afip_code
                    ds = line.name
                    qty = line.quantity
                    precio = line.price_unit
                    importe = line.price_subtotal
                    bonif = (
                        line.discount and str("%.2f" % (precio * qty - importe)) or None
                    )
                    if afip_ws in ["wsmtxca", "wsbfe"]:

                        iva_id = line.vat_tax_id.tax_group_id.l10n_ar_vat_afip_code
                        vat_taxes_amounts = line.vat_tax_id.compute_all(
                            line.price_unit,
                            inv.currency_id,
                            line.quantity,
                            product=line.product_id,
                            partner=inv.partner_id,
                        )
                        imp_iva = sum([x["amount"] for x in vat_taxes_amounts["taxes"]])
                        if afip_ws == "wsmtxca":
                            raise UserError(_("WS wsmtxca Not implemented yet"))
                        elif afip_ws == "wsbfe":
                            sec = ""
                            ws.AgregarItem(
                                codigo,
                                sec,
                                ds,
                                qty,
                                umed,
                                precio,
                                bonif,
                                iva_id,
                                importe + imp_iva,
                            )
                    elif afip_ws == "wsfex":
                        ws.AgregarItem(
                            codigo, ds, qty, umed, precio, "%.2f" % importe, bonif
                        )

            vto = None
            msg = False
            try:
                if afip_ws == "wsfe":
                    ws.CAESolicitar()
                    vto = ws.Vencimiento
                elif afip_ws == "wsmtxca":
                    ws.AutorizarComprobante()
                    vto = ws.Vencimiento
                elif afip_ws == "wsfex":
                    ws.Authorize(inv.id)
                    vto = ws.FchVencCAE
                elif afip_ws == "wsbfe":
                    ws.Authorize(inv.id)
                    vto = ws.Vencimiento
            except SoapFault as fault:
                msg = "Falla SOAP %s: %s" % (fault.faultcode, fault.faultstring)
            except Exception as e:
                msg = e
            except Exception:
                if ws.Excepcion:
                    msg = ws.Excepcion
                else:
                    msg = traceback.format_exception_only(sys.exc_type, sys.exc_value)[
                        0
                    ]
            if msg:
                _logger.info(
                    _("AFIP Validation Error. %s" % msg)
                    + " XML Request: %s XML Response: %s"
                    % (ws.XmlRequest, ws.XmlResponse)
                )
                raise UserError(_("AFIP Validation Error. %s" % msg))

            msg = "\n".join([ws.Obs or "", ws.ErrMsg or ""])
            if not ws.CAE or ws.Resultado != "A":
                raise UserError(_("AFIP Validation Error. %s" % msg))

            if vto:
                vto = datetime.strptime(vto, "%Y%m%d").date()
            _logger.info(
                "CAE solicitado con exito. CAE: %s. Resultado %s"
                % (ws.CAE, ws.Resultado)
            )
            inv.write(
                {
                    "afip_auth_mode": "CAE",
                    "afip_auth_code": ws.CAE,
                    "afip_auth_code_due": vto,
                    "afip_result": ws.Resultado,
                    "afip_message": msg,
                    "afip_xml_request": ws.XmlRequest,
                    "afip_xml_response": ws.XmlResponse,
                }
            )
            inv._cr.commit()

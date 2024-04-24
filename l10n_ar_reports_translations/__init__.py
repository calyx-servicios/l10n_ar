from odoo import api, SUPERUSER_ID


def post_init_hook(cr, REGISTRY):
    env = api.Environment(cr, SUPERUSER_ID, {})
    es_AR_id = env.ref("base.lang_es_AR")
    mods = env["ir.module.module"].search([("state", "=", "installed")])
    mods.with_context(overwrite=True)._update_translations(es_AR_id.code)
    env.cr.execute("ANALYZE ir_translation")

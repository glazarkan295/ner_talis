import os,sys,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
from services import effect_constructor_service as effects
from services.derived_stats_service import equipment_modifier_totals, external_effect_modifier_totals

class EffectConstructorRuntimeTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.saved=os.environ.get("EFFECT_CONSTRUCTOR_PATH"); os.environ["EFFECT_CONSTRUCTOR_PATH"]=str(Path(self.tmp.name)/"effects.json"); self.addCleanup(self.restore)
        effects.store().create("might",{"effect_name":"Мощь","effect_type":"stat_modifier","stat":"strength","value":7,"show_to_player":True,"player_text":"Сила увеличена"})
        effects.store().set_status("might",effects.STATUS_PUBLISHED,force=True)
    def restore(self):
        if self.saved is None: os.environ.pop("EFFECT_CONSTRUCTOR_PATH",None)
        else: os.environ["EFFECT_CONSTRUCTOR_PATH"]=self.saved
    def test_active_effect_id_resolves_published_definition(self):
        totals=external_effect_modifier_totals({"active_effects":[{"effect_id":"might"}]})
        self.assertEqual(totals["bonus_strength"],7)
    def test_equipped_item_passive_effect_link_is_live(self):
        totals=equipment_modifier_totals({"equipment":{"ring":{"effect_links":[{"effect_id":"might","trigger":"passive"}]}}})
        self.assertEqual(totals["bonus_strength"],7)
    def test_disabled_definition_no_longer_applies(self):
        effects.store().set_status("might",effects.STATUS_DISABLED,force=True)
        self.assertEqual(external_effect_modifier_totals({"active_effects":[{"effect_id":"might"}]}),{})

if __name__=="__main__":unittest.main()

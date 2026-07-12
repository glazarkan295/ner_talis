import sys, unittest
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from services.container_item_runtime import open_container

class ContainerItemRuntimeTest(unittest.TestCase):
 def test_open_consumes_one_and_grants_configured_reward(self):
  player={"inventory":[{"item_id":"chest","name":"Chest","amount":2}]}
  definition={"id":"chest","can_open":True,"consume_on_open":True,"guaranteed_rewards":[{"item_id":"gem","amount":3,"guaranteed":True}]}
  with patch("services.container_item_runtime.definition",return_value=definition):result=open_container(player,0)
  self.assertEqual(result["granted"],[{"item_id":"gem","amount":3,"text":None}])
  self.assertTrue(any(row.get("item_id")=="chest" and row.get("amount")==1 for row in player["inventory"]))
  self.assertTrue(any(row.get("item_id")=="gem" and row.get("amount")==3 for row in player["inventory"]))

 def test_failure_rolls_back_container_and_rewards(self):
  player={"inventory":[{"item_id":"chest","name":"Chest","amount":1}],"marker":"before"}
  before={"inventory":[{"item_id":"chest","name":"Chest","amount":1}],"marker":"before"}
  definition={"id":"chest","can_open":True,"guaranteed_rewards":[{"item_id":"gem","amount":1}]}
  class Failed:added=0;discarded=1
  with patch("services.container_item_runtime.definition",return_value=definition),patch("services.container_item_runtime.add_inventory_item",return_value=Failed()):
   with self.assertRaises(ValueError):open_container(player,0)
  self.assertEqual(player,before)

if __name__=="__main__":unittest.main()

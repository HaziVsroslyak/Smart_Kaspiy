import unittest
from api.routers.customs import generate_customs_demo,clear_customs
from api.schemas import CustomsRequest
class CustomsDemoTests(unittest.TestCase):
    def test_generated_manifests_go_through_real_verifier(self):
        for tampered in (False,True):
            for _ in range(5):
                sample=generate_customs_demo(tampered)
                result=clear_customs(CustomsRequest(cargo_payload=sample.cargo_payload,provided_hash=sample.provided_hash))
                self.assertEqual(result.status,sample.expected_status)
                self.assertEqual(result.green_corridor,not tampered)
                self.assertEqual(len(sample.provided_hash),64)
                self.assertEqual(sample.data_source,'synthetic')

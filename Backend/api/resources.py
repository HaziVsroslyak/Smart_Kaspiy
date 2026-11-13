"""ML and graph resources initialized by the application lifecycle."""
from __future__ import annotations

from dataclasses import dataclass
import networkx as nx
from ml_predictor import TransitPredictor, generate_mock_data
from ml_pipeline import CaspianPredictor, generate_mock_data as generate_caspian_data
from routing_engine import create_transport_graph
from demo_models import get_demo_models, DemoModels


@dataclass(frozen=True)
class RoutingResources:
    predictor: TransitPredictor
    graph: nx.MultiDiGraph
    caspian_predictor: CaspianPredictor
    demo: DemoModels


def build_resources() -> RoutingResources:
    predictor = TransitPredictor().train(generate_mock_data())
    caspian_predictor = CaspianPredictor().train(generate_caspian_data())
    return RoutingResources(predictor, create_transport_graph(), caspian_predictor, get_demo_models())

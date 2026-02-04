import salt.tracing.setup
from salt.tracing import get_tracing_manager, setup_tracing
from tests.support.mock import patch


def test_uses_bogo_if_no_opts():
    with patch("salt.tracing.bogo") as bogo_mock:
        setup_tracing({})
        assert get_tracing_manager() == bogo_mock.initialize.return_value


def test_uses_otel_if_configured():
    with patch("salt.tracing.otel") as otel_mock:
        setup_tracing({"tracing": {"module": {"otel": {}}}})
        assert get_tracing_manager() == otel_mock.initialize.return_value


def test_uses_bogo_if_otel_configured_but_not_installed():
    with patch.object(salt.tracing, "otel", None), patch(
        "salt.tracing.bogo"
    ) as bogo_mock:
        setup_tracing({"tracing": {"module": {"otel": {}}}})
        assert get_tracing_manager() == bogo_mock.initialize.return_value


def test_uses_bogo_if_otel_initialise_fails():
    with patch("salt.tracing.otel") as otel_mock, patch(
        "salt.tracing.bogo"
    ) as bogo_mock:
        otel_mock.initialize.side_effect = Exception
        setup_tracing({"tracing": {"module": {"otel": {}}}})
        assert get_tracing_manager() == bogo_mock.initialize.return_value

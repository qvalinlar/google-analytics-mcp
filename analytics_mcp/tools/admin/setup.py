# Qvalento additions to the Google Analytics MCP server.
# Read-only tools for auditing how a property is set up.

"""Tools for auditing a Google Analytics property's data collection setup."""

import asyncio
from typing import Any, Callable, Dict

from google.analytics import admin_v1alpha

from analytics_mcp.tools.client import create_admin_alpha_api_client
from analytics_mcp.tools.utils import construct_property_rn, proto_to_dict

_WEB_STREAM = admin_v1alpha.DataStream.DataStreamType.WEB_DATA_STREAM


def _safe(lookup: Callable[[], Any]) -> Any:
    """Runs one Admin API lookup and returns its result, or the error as text.

    One setting the user can't read (for example because of their role on the
    property) shouldn't hide all the others.
    """
    try:
        return lookup()
    except Exception as exc:  # pylint: disable=broad-except
        return {"error": f"{type(exc).__name__}: {exc}"}


async def get_property_setup(property_id: int | str) -> Dict[str, Any]:
    """Returns how a property is set up for data collection, in one call.

    Use this when auditing a property or explaining unexpected numbers. It
    returns the property's data retention, attribution and Google signals
    settings, and for each data stream its measurement ID and default URL.
    For web streams it also returns the enhanced measurement settings, the
    data redaction settings and the names of the Measurement Protocol secrets
    (never the secret values).

    Args:
        property_id: The Google Analytics property ID. Accepted formats are:
          - A number
          - A string consisting of 'properties/' followed by a number
    """
    prop = construct_property_rn(property_id)

    def _sync_call() -> Dict[str, Any]:
        client = create_admin_alpha_api_client()
        setup: Dict[str, Any] = {
            "data_retention": _safe(
                lambda: proto_to_dict(
                    client.get_data_retention_settings(
                        name=f"{prop}/dataRetentionSettings"
                    )
                )
            ),
            "attribution": _safe(
                lambda: proto_to_dict(
                    client.get_attribution_settings(
                        name=f"{prop}/attributionSettings"
                    )
                )
            ),
            "google_signals": _safe(
                lambda: proto_to_dict(
                    client.get_google_signals_settings(
                        name=f"{prop}/googleSignalsSettings"
                    )
                )
            ),
        }

        streams = []
        for stream in client.list_data_streams(parent=prop):
            entry = proto_to_dict(stream)
            if stream.type_ == _WEB_STREAM:
                entry["enhanced_measurement"] = _safe(
                    lambda: proto_to_dict(
                        client.get_enhanced_measurement_settings(
                            name=f"{stream.name}/enhancedMeasurementSettings"
                        )
                    )
                )
                entry["data_redaction"] = _safe(
                    lambda: proto_to_dict(
                        client.get_data_redaction_settings(
                            name=f"{stream.name}/dataRedactionSettings"
                        )
                    )
                )
                entry["measurement_protocol_secret_names"] = _safe(
                    lambda: [
                        secret.display_name
                        for secret in client.list_measurement_protocol_secrets(
                            parent=stream.name
                        )
                    ]
                )
            streams.append(entry)
        setup["data_streams"] = streams
        return setup

    return await asyncio.to_thread(_sync_call)
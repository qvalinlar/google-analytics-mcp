# Qvalento additions to the Google Analytics MCP server.
# Read-only tools for auditing how a property is set up.

"""Tools for auditing a Google Analytics property's data collection setup."""

import asyncio
from typing import Any, Callable, Dict, Iterable, List

from google.analytics import admin_v1alpha

from analytics_mcp.tools.client import create_admin_alpha_api_client
from analytics_mcp.tools.utils import construct_property_rn, proto_to_dict

_WEB_STREAM = admin_v1alpha.DataStream.DataStreamType.WEB_DATA_STREAM
_ROLLUP = admin_v1alpha.PropertyType.PROPERTY_TYPE_ROLLUP
_SUBPROPERTY = admin_v1alpha.PropertyType.PROPERTY_TYPE_SUBPROPERTY


def _safe(lookup: Callable[[], Any]) -> Any:
    """Runs one Admin API lookup and returns its result, or the error as text.

    One setting the user can't read (for example because of their role on the
    property) shouldn't hide all the others.
    """
    try:
        return lookup()
    except Exception as exc:  # pylint: disable=broad-except
        return {"error": f"{type(exc).__name__}: {exc}"}


def _all(pager: Iterable[Any]) -> List[Dict[str, Any]]:
    """Reads every page of a list call and converts each item to a dict."""
    return [proto_to_dict(item) for item in pager]


async def get_property_setup(property_id: int | str) -> Dict[str, Any]:
    """Returns how a property is set up for data collection, in one call.

    Use this when auditing a property or explaining unexpected numbers. It
    returns:
      - property settings: data retention, attribution, Google signals,
        reporting identity (which, together with Google signals, decides when
        GA4 applies thresholds and hides small numbers), user-provided data
        collection, and the account's data sharing settings;
      - integrations: BigQuery export links and their configuration, Firebase,
        Display & Video 360 and Search Ads 360 links, roll-up property sources
        (roll-up properties only) and subproperty event filters and sync
        settings (subproperties only). Google Ads links are returned by
        list_google_ads_links instead;
      - for each data stream: its measurement ID and default URL, and the
        event create rules and event edit rules configured in GA4. These
        rename, change or create events after collection, so they explain
        event counts that don't match the tagging in Google Tag Manager;
      - for web streams also: enhanced measurement settings, data redaction
        settings and the names of the Measurement Protocol secrets (never the
        secret values).

    Args:
        property_id: The Google Analytics property ID. Accepted formats are:
          - A number
          - A string consisting of 'properties/' followed by a number
    """
    prop = construct_property_rn(property_id)

    def _sync_call() -> Dict[str, Any]:
        client = create_admin_alpha_api_client()
        prop_info = client.get_property(name=prop)
        account = prop_info.account or prop_info.parent

        setup: Dict[str, Any] = {
            "property_type": prop_info.property_type.name,
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
            "reporting_identity": _safe(
                lambda: proto_to_dict(
                    client.get_reporting_identity_settings(
                        name=f"{prop}/reportingIdentitySettings"
                    )
                )
            ),
            "user_provided_data": _safe(
                lambda: proto_to_dict(
                    client.get_user_provided_data_settings(
                        name=f"{prop}/userProvidedDataSettings"
                    )
                )
            ),
            "account_data_sharing": _safe(
                lambda: proto_to_dict(
                    client.get_data_sharing_settings(
                        name=f"{account}/dataSharingSettings"
                    )
                )
            ),
        }

        integrations: Dict[str, Any] = {
            "bigquery_links": _safe(
                lambda: _all(client.list_big_query_links(parent=prop))
            ),
            "firebase_links": _safe(
                lambda: _all(client.list_firebase_links(parent=prop))
            ),
            "display_video_360_links": _safe(
                lambda: _all(
                    client.list_display_video360_advertiser_links(parent=prop)
                )
            ),
            "search_ads_360_links": _safe(
                lambda: _all(client.list_search_ads360_links(parent=prop))
            ),
        }
        if prop_info.property_type == _ROLLUP:
            integrations["rollup_source_properties"] = _safe(
                lambda: _all(
                    client.list_rollup_property_source_links(parent=prop)
                )
            )
        if prop_info.property_type == _SUBPROPERTY:
            integrations["subproperty_event_filters"] = _safe(
                lambda: _all(client.list_subproperty_event_filters(parent=prop))
            )
            integrations["subproperty_sync_configs"] = _safe(
                lambda: _all(client.list_subproperty_sync_configs(parent=prop))
            )
        setup["integrations"] = integrations

        streams = []
        for stream in client.list_data_streams(parent=prop):
            entry = proto_to_dict(stream)
            entry["event_create_rules"] = _safe(
                lambda: _all(client.list_event_create_rules(parent=stream.name))
            )
            entry["event_edit_rules"] = _safe(
                lambda: _all(client.list_event_edit_rules(parent=stream.name))
            )
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


async def get_property_definitions(property_id: int | str) -> Dict[str, Any]:
    """Returns the logic behind a property's calculated metrics, custom channel groups and audiences.

    Use this to explain how a metric, channel or audience in reports is
    defined. It returns:
      - calculated metrics with their formulas (for example the formula behind
        "Items conversion rate");
      - channel groups with their rules, including custom groups such as
        "Default Channel Group 2.0" and the system default group;
      - audiences with their conditions, membership duration in days and
        whether they're available for ads personalization, which matters when
        audiences are shared with Google Ads.

    Custom dimensions and metrics are returned by
    get_custom_dimensions_and_metrics instead.

    Args:
        property_id: The Google Analytics property ID. Accepted formats are:
          - A number
          - A string consisting of 'properties/' followed by a number
    """
    prop = construct_property_rn(property_id)

    def _sync_call() -> Dict[str, Any]:
        client = create_admin_alpha_api_client()
        return {
            "calculated_metrics": _safe(
                lambda: _all(client.list_calculated_metrics(parent=prop))
            ),
            "channel_groups": _safe(
                lambda: _all(client.list_channel_groups(parent=prop))
            ),
            "audiences": _safe(lambda: _all(client.list_audiences(parent=prop))),
        }

    return await asyncio.to_thread(_sync_call)

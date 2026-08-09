"""
Recommendation Templates Module.

Provides pre-built, reusable remediation templates for network congestion, latency spikes,
packet drops, routing instability, WAN failures, link saturation, and VPN tunnel failures.
"""

from typing import Any, Dict, List

from agents.recommendation.recommendation_models import RiskLevel


class RecommendationTemplateRegistry:
    """
    Registry providing reusable remediation templates.
    """

    TEMPLATES: Dict[str, Dict[str, Any]] = {
        "NETWORK_CONGESTION": {
            "summary": "Apply egress QoS bandwidth shaping and re-route bulk traffic to secondary WAN path.",
            "root_cause_hypothesis": "Peak traffic volume exceeding primary link capacity bandwidth limits.",
            "recommended_actions": [
                "Activate QoS shaping policy on interface egress queue.",
                "Adjust BGP local preference to shift non-critical traffic to secondary uplink.",
                "Verify interface queue counters and drop rate recovery.",
            ],
            "actions": [
                {
                    "title": "Configure Egress QoS Shaping",
                    "description": "Apply policy-map SHAPE_EGRESS to interface to prioritize latency-sensitive traffic.",
                    "sequence_order": 1,
                    "cli_commands": [
                        {
                            "command_text": "policy-map SHAPE_EGRESS\n class class-default\n  shape average 95000000",
                            "description": "Create QoS shaping policy map",
                            "platform": "cisco_ios",
                            "is_reversable": True,
                        },
                        {
                            "command_text": "interface {interface}\n service-policy output SHAPE_EGRESS",
                            "description": "Attach policy map to egress interface",
                            "platform": "cisco_ios",
                            "is_reversable": True,
                        },
                    ],
                    "verification_commands": [
                        {
                            "command_text": "show policy-map interface {interface}",
                            "description": "Check QoS policy drops and matched packets",
                            "platform": "cisco_ios",
                            "is_reversable": True,
                        }
                    ],
                },
                {
                    "title": "BGP Route Preference Adjustment",
                    "description": "Increase local preference for secondary path to balance traffic load.",
                    "sequence_order": 2,
                    "cli_commands": [
                        {
                            "command_text": "route-map SEC_WAN_PREF permit 10\n set local-preference 200",
                            "description": "Set higher BGP local preference for secondary link",
                            "platform": "cisco_ios",
                            "is_reversable": True,
                        }
                    ],
                    "verification_commands": [
                        {
                            "command_text": "show ip bgp summary",
                            "description": "Verify BGP neighbor state and prefix updates",
                            "platform": "cisco_ios",
                            "is_reversable": True,
                        }
                    ],
                },
            ],
            "rollback_plan": {
                "steps": [
                    "Detach service-policy from interface",
                    "Remove policy-map SHAPE_EGRESS definition",
                    "Reset BGP route-map local preference to default",
                ],
                "rollback_commands": [
                    {
                        "command_text": "interface {interface}\n no service-policy output SHAPE_EGRESS",
                        "description": "Remove QoS service policy",
                        "platform": "cisco_ios",
                        "is_reversable": True,
                    },
                    {
                        "command_text": "no policy-map SHAPE_EGRESS",
                        "description": "Delete policy map definition",
                        "platform": "cisco_ios",
                        "is_reversable": True,
                    },
                ],
                "estimated_rollback_duration_min": 2.0,
            },
            "impact_assessment": {
                "business_impact": "MODERATE_BUSINESS_IMPACT",
                "affected_services": ["WAN Transport", "Bulk Data Transfers"],
                "risk_level": RiskLevel.LOW,
                "downtime_expected": False,
            },
            "estimated_duration_min": 4.0,
            "automation_possible": True,
            "cited_sources": [
                "cisco_qos_configuration_guide.pdf",
                "network_architecture_standard.txt",
            ],
        },
        "LATENCY_SPIKE": {
            "summary": "Clear queue buffers and adjust TCP window scaling to stabilize RTT latency.",
            "root_cause_hypothesis": "Transient bufferbloat or queuing delay on interface transmit buffer.",
            "recommended_actions": [
                "Inspect interface buffer allocations.",
                "Enable Fair-Queueing on transmit interface.",
                "Verify latency metrics drop back to baseline.",
            ],
            "actions": [
                {
                    "title": "Enable Fair-Queueing",
                    "description": "Apply fair-queueing to prevent single stream from starving interface buffers.",
                    "sequence_order": 1,
                    "cli_commands": [
                        {
                            "command_text": "interface {interface}\n fair-queue",
                            "description": "Enable weighted fair queueing",
                            "platform": "cisco_ios",
                            "is_reversable": True,
                        }
                    ],
                    "verification_commands": [
                        {
                            "command_text": "show interface {interface} | include drops|queue",
                            "description": "Verify interface queue stats",
                            "platform": "cisco_ios",
                            "is_reversable": True,
                        }
                    ],
                }
            ],
            "rollback_plan": {
                "steps": ["Disable fair-queueing on interface"],
                "rollback_commands": [
                    {
                        "command_text": "interface {interface}\n no fair-queue",
                        "description": "Disable fair queueing",
                        "platform": "cisco_ios",
                        "is_reversable": True,
                    }
                ],
                "estimated_rollback_duration_min": 1.0,
            },
            "impact_assessment": {
                "business_impact": "LOW_BUSINESS_IMPACT",
                "affected_services": ["Interactive VoIP", "Real-Time Telemetry"],
                "risk_level": RiskLevel.LOW,
                "downtime_expected": False,
            },
            "estimated_duration_min": 3.0,
            "automation_possible": True,
            "cited_sources": ["wan_latency_troubleshooting_runbook.md"],
        },
        "EGRESS_PACKET_DROPS": {
            "summary": "Expand interface ring buffer size and check physical layer errors.",
            "root_cause_hypothesis": "Egress interface ring buffer exhaustion during bursty traffic.",
            "recommended_actions": [
                "Increase interface TX ring buffer length.",
                "Check transceiver optical power and CRC error counters.",
            ],
            "actions": [
                {
                    "title": "Expand TX Ring Buffer",
                    "description": "Increase ring buffer from 256 to 1024 descriptors.",
                    "sequence_order": 1,
                    "cli_commands": [
                        {
                            "command_text": "interface {interface}\n tx-ring-limit 1024",
                            "description": "Set TX ring limit",
                            "platform": "cisco_ios",
                            "is_reversable": True,
                        }
                    ],
                    "verification_commands": [
                        {
                            "command_text": "show controllers Ethernet-Internal | include Ring",
                            "description": "Check ring descriptor count",
                            "platform": "cisco_ios",
                            "is_reversable": True,
                        }
                    ],
                }
            ],
            "rollback_plan": {
                "steps": ["Restore TX ring limit to default"],
                "rollback_commands": [
                    {
                        "command_text": "interface {interface}\n no tx-ring-limit",
                        "description": "Reset TX ring limit",
                        "platform": "cisco_ios",
                        "is_reversable": True,
                    }
                ],
                "estimated_rollback_duration_min": 1.0,
            },
            "impact_assessment": {
                "business_impact": "MODERATE_BUSINESS_IMPACT",
                "affected_services": ["Data Plane Egress"],
                "risk_level": RiskLevel.LOW,
                "downtime_expected": False,
            },
            "estimated_duration_min": 3.0,
            "automation_possible": True,
            "cited_sources": ["buffer_tuning_guide.txt"],
        },
        "ROUTING_INSTABILITY": {
            "summary": "Apply BGP route dampening and extend hold-time timer to suppress flap propagation.",
            "root_cause_hypothesis": "Unstable peering session causing BGP route flap propagation.",
            "recommended_actions": [
                "Configure BGP route dampening parameters.",
                "Increase BGP keepalive and holdtime timers.",
            ],
            "actions": [
                {
                    "title": "BGP Route Dampening",
                    "description": "Enable dampening to penalize flapping prefixes.",
                    "sequence_order": 1,
                    "cli_commands": [
                        {
                            "command_text": "router bgp 65000\n bgp dampening 15 750 2000 60",
                            "description": "Enable BGP route dampening",
                            "platform": "cisco_ios",
                            "is_reversable": True,
                        }
                    ],
                    "verification_commands": [
                        {
                            "command_text": "show ip bgp dampened-paths",
                            "description": "List penalized BGP routes",
                            "platform": "cisco_ios",
                            "is_reversable": True,
                        }
                    ],
                }
            ],
            "rollback_plan": {
                "steps": ["Disable BGP route dampening"],
                "rollback_commands": [
                    {
                        "command_text": "router bgp 65000\n no bgp dampening",
                        "description": "Disable route dampening",
                        "platform": "cisco_ios",
                        "is_reversable": True,
                    }
                ],
                "estimated_rollback_duration_min": 2.0,
            },
            "impact_assessment": {
                "business_impact": "HIGH_BUSINESS_IMPACT",
                "affected_services": ["Core Routing", "BGP Peering"],
                "risk_level": RiskLevel.MEDIUM,
                "downtime_expected": False,
            },
            "estimated_duration_min": 5.0,
            "automation_possible": True,
            "cited_sources": ["bgp_peering_security_policy.pdf"],
        },
        "WAN_FAILURE": {
            "summary": "Initiate automated failover to secondary WAN transport link.",
            "root_cause_hypothesis": "Primary WAN link degradation or complete circuit failure.",
            "recommended_actions": [
                "Verify SLA probe status.",
                "Switch default route to secondary WAN gateway.",
            ],
            "actions": [
                {
                    "title": "WAN Failover Switch",
                    "description": "Update static floating default route tracking.",
                    "sequence_order": 1,
                    "cli_commands": [
                        {
                            "command_text": "ip route 0.0.0.0 0.0.0.0 {interface} track 10",
                            "description": "Failover default gateway route",
                            "platform": "cisco_ios",
                            "is_reversable": True,
                        }
                    ],
                    "verification_commands": [
                        {
                            "command_text": "show track 10",
                            "description": "Check IP SLA track state",
                            "platform": "cisco_ios",
                            "is_reversable": True,
                        }
                    ],
                }
            ],
            "rollback_plan": {
                "steps": ["Restore primary WAN gateway route"],
                "rollback_commands": [
                    {
                        "command_text": "no ip route 0.0.0.0 0.0.0.0 {interface} track 10",
                        "description": "Restore primary route",
                        "platform": "cisco_ios",
                        "is_reversable": True,
                    }
                ],
                "estimated_rollback_duration_min": 2.0,
            },
            "impact_assessment": {
                "business_impact": "CRITICAL_BUSINESS_IMPACT",
                "affected_services": ["WAN Connectivity", "Branch Office Access"],
                "risk_level": RiskLevel.HIGH,
                "downtime_expected": False,
            },
            "estimated_duration_min": 5.0,
            "automation_possible": True,
            "cited_sources": ["sdwan_failover_playbook.md"],
        },
    }

    @classmethod
    def get_template(cls, incident_type: str) -> Dict[str, Any]:
        """
        Retrieve remediation template dictionary for a given incident_type.

        Args:
            incident_type: Incident category string.

        Returns:
            Template dictionary.
        """
        if incident_type in cls.TEMPLATES:
            return cls.TEMPLATES[incident_type]

        # Default fallback template
        return {
            "summary": "Perform diagnostic interface check and verify telemetry baselines.",
            "root_cause_hypothesis": "Unspecified predictive metric anomaly.",
            "recommended_actions": [
                "Inspect interface status and counter metrics.",
                "Review recent configuration changes.",
                "Verify upstream link health.",
            ],
            "actions": [
                {
                    "title": "Diagnostic Interface Verification",
                    "description": "Run standard diagnostic status commands.",
                    "sequence_order": 1,
                    "cli_commands": [
                        {
                            "command_text": "show interface {interface}",
                            "description": "Check interface status and error counters",
                            "platform": "cisco_ios",
                            "is_reversable": True,
                        }
                    ],
                    "verification_commands": [
                        {
                            "command_text": "show logging | include {interface}",
                            "description": "Check syslog for interface events",
                            "platform": "cisco_ios",
                            "is_reversable": True,
                        }
                    ],
                }
            ],
            "rollback_plan": {
                "steps": ["No configuration changes made"],
                "rollback_commands": [],
                "estimated_rollback_duration_min": 0.0,
            },
            "impact_assessment": {
                "business_impact": "LOW_BUSINESS_IMPACT",
                "affected_services": [],
                "risk_level": RiskLevel.LOW,
                "downtime_expected": False,
            },
            "estimated_duration_min": 2.0,
            "automation_possible": True,
            "cited_sources": ["standard_noc_triage_sop.md"],
        }

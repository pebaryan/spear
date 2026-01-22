#!/usr/bin/env python3
"""
Team Forming Process Tests
Tests the team forming BPMN process with event-based gateway
"""

import pytest
from rdflib import Graph, Namespace, URIRef, Literal, RDF
import tempfile
import io


class TestTeamFormingProcess:
    """Test the complete team forming process with event-based gateway"""

    @pytest.fixture
    def storage(self):
        from src.api.storage import RDFStorageService

        temp_dir = tempfile.mkdtemp()
        storage = RDFStorageService(storage_path=temp_dir)
        yield storage
        import shutil

        shutil.rmtree(temp_dir, ignore_errors=True)

    @pytest.fixture
    def team_forming_bpmn(self):
        """Return the team forming BPMN process definition"""
        return """<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL"
                          xmlns:camunda="http://camunda.org/schema/1.0/bpmn"
                          targetNamespace="http://bpmn.io/schema/team-forming">
            <bpmn:message id="invitationAccepted" name="invitationAccepted"/>
            <bpmn:message id="invitationRejected" name="invitationRejected"/>
            <bpmn:message id="invitationCancelled" name="invitationCancelled"/>
            <bpmn:message id="responseRevoked" name="responseRevoked"/>
            
            <bpmn:process id="teamFormingProcess" name="Team Forming Process" isExecutable="true">
                <bpmn:startEvent id="startInvite" name="Start Invitation"/>
                
                <bpmn:serviceTask id="taskCreateInvitation" name="Create Invitation Record"
                                  camunda:topic="create_invitation"/>
                <bpmn:serviceTask id="taskSendInvitation" name="Send Invitation Email"
                                  camunda:topic="send_invitation_email"/>
                
                <bpmn:eventBasedGateway id="gatewayEventResponse" name="Wait for Response Events"/>
                
                <bpmn:receiveTask id="taskAcceptInvitation" name="Wait: Invitation Accepted"
                                  camunda:message="invitationAccepted"/>
                <bpmn:receiveTask id="taskRejectInvitation" name="Wait: Invitation Rejected"
                                  camunda:message="invitationRejected"/>
                <bpmn:receiveTask id="taskCancelInvitation" name="Wait: Invitation Cancelled"
                                  camunda:message="invitationCancelled"/>
                <bpmn:receiveTask id="taskRevokeResponse" name="Wait: Response Revoked"
                                  camunda:message="responseRevoked"/>
                
                <bpmn:exclusiveGateway id="gatewayRouteResponse" name="Route by Response"/>
                
                <bpmn:serviceTask id="taskProcessAcceptance" name="Process Acceptance"
                                  camunda:topic="process_acceptance"/>
                <bpmn:serviceTask id="taskProcessRejection" name="Process Rejection"
                                  camunda:topic="process_rejection"/>
                <bpmn:serviceTask id="taskProcessCancellation" name="Process Cancellation"
                                  camunda:topic="process_cancellation"/>
                <bpmn:serviceTask id="taskProcessRevocation" name="Process Revocation"
                                  camunda:topic="process_revocation"/>
                
                <bpmn:endEvent id="endAccepted" name="Invitation Accepted"/>
                <bpmn:endEvent id="endRejected" name="Invitation Rejected"/>
                <bpmn:endEvent id="endCancelled" name="Invitation Cancelled"/>
                <bpmn:endEvent id="endRevoked" name="Response Revoked"/>
                
                <bpmn:sequenceFlow id="flowStart" sourceRef="startInvite" targetRef="taskCreateInvitation"/>
                <bpmn:sequenceFlow id="flowCreateInvitation" sourceRef="taskCreateInvitation" targetRef="taskSendInvitation"/>
                <bpmn:sequenceFlow id="flowWaitForResponse" sourceRef="taskSendInvitation" targetRef="gatewayEventResponse"/>
                
                <bpmn:sequenceFlow id="flowToAccept" sourceRef="gatewayEventResponse" targetRef="taskAcceptInvitation"/>
                <bpmn:sequenceFlow id="flowToReject" sourceRef="gatewayEventResponse" targetRef="taskRejectInvitation"/>
                <bpmn:sequenceFlow id="flowToCancel" sourceRef="gatewayEventResponse" targetRef="taskCancelInvitation"/>
                <bpmn:sequenceFlow id="flowToRevoke" sourceRef="gatewayEventResponse" targetRef="taskRevokeResponse"/>
                
                <bpmn:sequenceFlow id="flowFromAccept" sourceRef="taskAcceptInvitation" targetRef="gatewayRouteResponse"/>
                <bpmn:sequenceFlow id="flowFromReject" sourceRef="taskRejectInvitation" targetRef="gatewayRouteResponse"/>
                <bpmn:sequenceFlow id="flowFromCancel" sourceRef="taskCancelInvitation" targetRef="gatewayRouteResponse"/>
                <bpmn:sequenceFlow id="flowFromRevoke" sourceRef="taskRevokeResponse" targetRef="gatewayRouteResponse"/>
                
                <bpmn:sequenceFlow id="flowToAcceptHandler" sourceRef="gatewayRouteResponse" targetRef="taskProcessAcceptance"/>
                <bpmn:sequenceFlow id="flowToRejectHandler" sourceRef="gatewayRouteResponse" targetRef="taskProcessRejection"/>
                <bpmn:sequenceFlow id="flowToCancelHandler" sourceRef="gatewayRouteResponse" targetRef="taskProcessCancellation"/>
                <bpmn:sequenceFlow id="flowToRevokeHandler" sourceRef="gatewayRouteResponse" targetRef="taskProcessRevocation"/>
                
                <bpmn:sequenceFlow id="flowAccepted" sourceRef="taskProcessAcceptance" targetRef="endAccepted"/>
                <bpmn:sequenceFlow id="flowRejected" sourceRef="taskProcessRejection" targetRef="endRejected"/>
                <bpmn:sequenceFlow id="flowCancelled" sourceRef="taskProcessCancellation" targetRef="endCancelled"/>
                <bpmn:sequenceFlow id="flowRevoked" sourceRef="taskProcessRevocation" targetRef="endRevoked"/>
            </bpmn:process>
        </bpmn:definitions>"""

    def test_deploy_team_forming_process(self, storage, team_forming_bpmn):
        """Test that team forming process can be deployed"""
        process_id = storage.deploy_process(
            name="Team Forming Process",
            description="Process for team member invitations",
            bpmn_content=team_forming_bpmn,
        )

        assert process_id is not None
        print(f"Deployed process: {process_id}")

        process_graph = storage.get_process_graph(process_id)
        assert len(process_graph) > 0
        print("Process graph created successfully")

    def test_invitation_workflow_accept(self, storage, team_forming_bpmn):
        """Test complete workflow: invitation accepted"""
        from rdflib import RDF
        from src.api.storage import INST

        process_id = storage.deploy_process(
            name="Team Forming Process",
            description="Test acceptance workflow",
            bpmn_content=team_forming_bpmn,
        )

        created_invitation = []

        def create_invitation_handler(instance_id, variables):
            created_invitation.append(
                {
                    "instance_id": instance_id,
                    "inviteeEmail": variables.get("inviteeEmail"),
                    "teamRole": variables.get("teamRole"),
                }
            )
            return {"invitationId": "INV-001", "status": "pending"}

        def send_email_handler(instance_id, variables):
            return {"emailSent": True, "inviteeEmail": variables.get("inviteeEmail")}

        def process_acceptance_handler(instance_id, variables):
            return {"memberAdded": True, "welcomeEmailSent": True}

        storage.register_topic_handler("create_invitation", create_invitation_handler)
        storage.register_topic_handler("send_invitation_email", send_email_handler)
        storage.register_topic_handler("process_acceptance", process_acceptance_handler)

        result = storage.create_instance(
            process_id=process_id,
            variables={
                "inviteeEmail": "new.member@example.com",
                "teamRole": "member",
            },
        )

        instance_id = result["id"]
        print(f"Created instance: {instance_id}")

        assert len(created_invitation) == 1
        assert created_invitation[0]["inviteeEmail"] == "new.member@example.com"
        assert created_invitation[0]["teamRole"] == "member"
        print("Invitation created successfully")

        waiting_count = 0
        for token_uri in storage.instances_graph.subjects(RDF.type, INST.Token):
            token_status = storage.instances_graph.value(token_uri, INST.status)
            if token_status and str(token_status) == "WAITING":
                waiting_count += 1

        assert waiting_count == 4, f"Should have 4 waiting tokens, got {waiting_count}"
        print(f"Event-based gateway created {waiting_count} waiting tokens")

        result = storage.send_message(
            message_name="invitationAccepted",
            instance_id=instance_id,
            variables={
                "responseTimestamp": "2024-01-22T10:30:00Z",
                "responseAction": "accept",
            },
        )

        assert result["status"] == "delivered", (
            f"Expected delivered, got {result['status']}"
        )
        assert result["matched_count"] == 1
        print(f"Message delivered: {result}")

    def test_invitation_workflow_reject(self, storage, team_forming_bpmn):
        """Test complete workflow: invitation rejected"""
        process_id = storage.deploy_process(
            name="Team Forming Process",
            description="Test rejection workflow",
            bpmn_content=team_forming_bpmn,
        )

        def create_invitation_handler(instance_id, variables):
            return {"invitationId": "INV-002", "status": "pending"}

        def send_email_handler(instance_id, variables):
            return {"emailSent": True}

        def process_rejection_handler(instance_id, variables):
            return {"rejectionLogged": True, "acknowledgmentSent": True}

        storage.register_topic_handler("create_invitation", create_invitation_handler)
        storage.register_topic_handler("send_invitation_email", send_email_handler)
        storage.register_topic_handler("process_rejection", process_rejection_handler)

        result = storage.create_instance(
            process_id=process_id,
            variables={
                "inviteeEmail": "declined.member@example.com",
                "teamRole": "reviewer",
            },
        )

        instance_id = result["id"]
        print(f"Created instance: {instance_id}")

        result = storage.send_message(
            message_name="invitationRejected",
            instance_id=instance_id,
            variables={
                "responseTimestamp": "2024-01-22T11:00:00Z",
                "reason": "Schedule conflict",
            },
        )

        assert result["status"] == "delivered"
        assert result["matched_count"] == 1
        print(f"Rejection message delivered: {result}")

    def test_invitation_workflow_cancel(self, storage, team_forming_bpmn):
        """Test complete workflow: invitation cancelled by leader"""
        process_id = storage.deploy_process(
            name="Team Forming Process",
            description="Test cancellation workflow",
            bpmn_content=team_forming_bpmn,
        )

        def create_invitation_handler(instance_id, variables):
            return {"invitationId": "INV-003", "status": "pending"}

        def send_email_handler(instance_id, variables):
            return {"emailSent": True}

        def process_cancellation_handler(instance_id, variables):
            return {"cancellationLogged": True, "notificationSent": True}

        storage.register_topic_handler("create_invitation", create_invitation_handler)
        storage.register_topic_handler("send_invitation_email", send_email_handler)
        storage.register_topic_handler(
            "process_cancellation", process_cancellation_handler
        )

        result = storage.create_instance(
            process_id=process_id,
            variables={
                "inviteeEmail": "cancelled.member@example.com",
                "teamRole": "lead",
            },
        )

        instance_id = result["id"]
        print(f"Created instance: {instance_id}")

        result = storage.send_message(
            message_name="invitationCancelled",
            instance_id=instance_id,
            variables={
                "cancelledBy": "leader@example.com",
                "reason": "Project requirements changed",
            },
        )

        assert result["status"] == "delivered"
        assert result["matched_count"] == 1
        print(f"Cancellation message delivered: {result}")

    def test_invitation_workflow_revoke(self, storage, team_forming_bpmn):
        """Test complete workflow: accepted member revokes response"""
        process_id = storage.deploy_process(
            name="Team Forming Process",
            description="Test revocation workflow",
            bpmn_content=team_forming_bpmn,
        )

        def create_invitation_handler(instance_id, variables):
            return {"invitationId": "INV-004", "status": "pending"}

        def send_email_handler(instance_id, variables):
            return {"emailSent": True}

        def process_acceptance_handler(instance_id, variables):
            return {"memberAdded": True}

        def process_revocation_handler(instance_id, variables):
            return {"memberRemoved": True, "leaderNotified": True}

        storage.register_topic_handler("create_invitation", create_invitation_handler)
        storage.register_topic_handler("send_invitation_email", send_email_handler)
        storage.register_topic_handler("process_acceptance", process_acceptance_handler)
        storage.register_topic_handler("process_revocation", process_revocation_handler)

        result = storage.create_instance(
            process_id=process_id,
            variables={
                "inviteeEmail": "revoked.member@example.com",
                "teamRole": "member",
            },
        )

        instance_id = result["id"]
        print(f"Created instance: {instance_id}")

        result = storage.send_message(
            message_name="invitationAccepted",
            instance_id=instance_id,
            variables={"responseAction": "accept"},
        )

        assert result["status"] == "delivered"
        print("Initial acceptance delivered")

        result = storage.send_message(
            message_name="responseRevoked",
            instance_id=instance_id,
            variables={
                "revocationReason": "Changed my mind",
                "revocationTimestamp": "2024-01-22T14:00:00Z",
            },
        )

        assert result["status"] == "delivered"
        assert result["matched_count"] == 1
        print(f"Revocation message delivered: {result}")

    def test_wrong_message_not_matched(self, storage, team_forming_bpmn):
        """Test that wrong message name doesn't match any receive task"""
        process_id = storage.deploy_process(
            name="Team Forming Process",
            description="Test non-matching message",
            bpmn_content=team_forming_bpmn,
        )

        def create_invitation_handler(instance_id, variables):
            return {"invitationId": "INV-005", "status": "pending"}

        def send_email_handler(instance_id, variables):
            return {"emailSent": True}

        storage.register_topic_handler("create_invitation", create_invitation_handler)
        storage.register_topic_handler("send_invitation_email", send_email_handler)

        result = storage.create_instance(
            process_id=process_id,
            variables={
                "inviteeEmail": "test@example.com",
                "teamRole": "member",
            },
        )

        instance_id = result["id"]

        result = storage.send_message(
            message_name="unknownMessage",
            instance_id=instance_id,
        )

        assert result["status"] == "no_match"
        assert result["matched_count"] == 0
        print(f"Wrong message correctly not matched: {result}")

    def test_message_with_variables(self, storage, team_forming_bpmn):
        """Test that message variables are stored correctly"""
        process_id = storage.deploy_process(
            name="Team Forming Process",
            description="Test variable passing",
            bpmn_content=team_forming_bpmn,
        )

        def create_invitation_handler(instance_id, variables):
            return {"invitationId": "INV-006", "status": "pending"}

        def send_email_handler(instance_id, variables):
            return {"emailSent": True}

        def process_acceptance_handler(instance_id, variables):
            response_timestamp = variables.get("responseTimestamp")
            response_action = variables.get("responseAction")
            assert response_timestamp == "2024-01-22T10:30:00Z"
            assert response_action == "accept"
            return {"memberAdded": True}

        storage.register_topic_handler("create_invitation", create_invitation_handler)
        storage.register_topic_handler("send_invitation_email", send_email_handler)
        storage.register_topic_handler("process_acceptance", process_acceptance_handler)

        result = storage.create_instance(
            process_id=process_id,
            variables={
                "inviteeEmail": "vars.test@example.com",
                "teamRole": "member",
            },
        )

        instance_id = result["id"]

        result = storage.send_message(
            message_name="invitationAccepted",
            instance_id=instance_id,
            variables={
                "responseTimestamp": "2024-01-22T10:30:00Z",
                "responseAction": "accept",
                "ipAddress": "192.168.1.100",
                "userAgent": "Mozilla/5.0",
            },
        )

        assert result["status"] == "delivered"
        print("Message with multiple variables delivered successfully")

    def test_instance_audit_log(self, storage, team_forming_bpmn):
        """Test that all events are logged in audit trail"""
        process_id = storage.deploy_process(
            name="Team Forming Process",
            description="Test audit logging",
            bpmn_content=team_forming_bpmn,
        )

        def create_invitation_handler(instance_id, variables):
            return {"invitationId": "INV-007", "status": "pending"}

        def send_email_handler(instance_id, variables):
            return {"emailSent": True}

        storage.register_topic_handler("create_invitation", create_invitation_handler)
        storage.register_topic_handler("send_invitation_email", send_email_handler)

        result = storage.create_instance(
            process_id=process_id,
            variables={
                "inviteeEmail": "audit.test@example.com",
                "teamRole": "reviewer",
            },
        )

        instance_id = result["id"]
        instance = storage.get_instance(instance_id)
        print(f"Instance created: {instance}")

        events = storage.get_instance_audit_log(instance_id)
        print(f"Audit events: {len(events)} events logged")

        event_types = [e["type"] for e in events]
        assert "CREATED" in event_types
        assert "SERVICE_TASK" in event_types
        assert "WAITING_FOR_MESSAGE" in event_types
        print(f"Event types: {event_types}")

    def test_multiple_instances_independent(self, storage, team_forming_bpmn):
        """Test that multiple instances are handled independently"""
        process_id = storage.deploy_process(
            name="Team Forming Process",
            description="Test multiple instances",
            bpmn_content=team_forming_bpmn,
        )

        def create_invitation_handler(instance_id, variables):
            return {"invitationId": f"INV-{instance_id[:8]}", "status": "pending"}

        def send_email_handler(instance_id, variables):
            return {"emailSent": True}

        def process_acceptance_handler(instance_id, variables):
            return {"memberAdded": True}

        storage.register_topic_handler("create_invitation", create_invitation_handler)
        storage.register_topic_handler("send_invitation_email", send_email_handler)
        storage.register_topic_handler("process_acceptance", process_acceptance_handler)

        result1 = storage.create_instance(
            process_id=process_id,
            variables={"inviteeEmail": "member1@example.com", "teamRole": "member"},
        )

        result2 = storage.create_instance(
            process_id=process_id,
            variables={"inviteeEmail": "member2@example.com", "teamRole": "lead"},
        )

        instance_id1 = result1["id"]
        instance_id2 = result2["id"]

        print(f"Instance 1: {instance_id1}")
        print(f"Instance 2: {instance_id2}")

        result = storage.send_message(
            message_name="invitationAccepted",
            instance_id=instance_id1,
        )

        assert result["status"] == "delivered"
        assert result["matched_count"] == 1
        print(f"Message to instance 1 delivered: {result}")

        result = storage.send_message(
            message_name="invitationRejected",
            instance_id=instance_id2,
        )

        assert result["status"] == "delivered"
        assert result["matched_count"] == 1
        print(f"Message to instance 2 delivered: {result}")

        print("Multiple instances handled independently - SUCCESS")


class TestTeamFormingMessageHandlers:
    """Test message handler registration and execution"""

    @pytest.fixture
    def storage(self):
        from src.api.storage import RDFStorageService

        temp_dir = tempfile.mkdtemp()
        storage = RDFStorageService(storage_path=temp_dir)
        yield storage
        import shutil

        shutil.rmtree(temp_dir, ignore_errors=True)

    def test_register_message_handler(self, storage):
        """Test registering a message handler"""

        def my_handler(instance_id, variables):
            return {"processed": True}

        result = storage.register_message_handler(
            message_name="testMessage",
            handler_function=my_handler,
            description="Test handler",
        )

        assert result is True
        assert "testMessage" in storage.message_handlers
        print(f"Registered message handler: {storage.message_handlers['testMessage']}")

    def test_unregister_message_handler(self, storage):
        """Test unregistering a message handler"""

        def my_handler(instance_id, variables):
            return {"processed": True}

        storage.register_message_handler(
            message_name="testMessage",
            handler_function=my_handler,
        )

        result = storage.unregister_message_handler("testMessage")
        assert result is True
        assert "testMessage" not in storage.message_handlers
        print("Message handler unregistered successfully")

        result = storage.unregister_message_handler("nonexistent")
        assert result is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

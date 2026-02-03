# status_machine.py
"""
Single Source of Truth für Status-Logik in NovaPact GCU.
Enterprise-taugliche Status-Maschine für AI-Governance mit HITL-Support.
"""

from enum import Enum
from typing import Dict, Set, Optional, List, Any, Tuple
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
import logging
import threading
from abc import ABC, abstractmethod
import json

# ==================== STATUS DEFINITION ====================

class SystemStatus(str, Enum):
    """Kanonische Status-Definition - Single Source of Truth"""
    OK = "ok"
    NEEDS_REVIEW = "needs_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    ERROR = "error"
    
    def __str__(self) -> str:
        return self.value

# ==================== TRANSITION REGELN ====================

class StatusTransitionError(Exception):
    """Exception für illegale Status-Übergänge"""
    def __init__(self, message: str, from_status: SystemStatus, to_status: SystemStatus):
        super().__init__(message)
        self.from_status = from_status
        self.to_status = to_status

class AdminOverrideError(Exception):
    """Exception für nicht autorisierte Admin-Overrides"""
    def __init__(self, message: str, actor: str, role: str):
        super().__init__(message)
        self.actor = actor
        self.role = role

@dataclass(frozen=True)
class TransitionContext:
    """Kontext für Status-Übergänge (Auditierbar)"""
    actor: str
    role: str
    auth_type: str
    timestamp: datetime
    reason: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_audit_dict(self) -> Dict[str, Any]:
        """Konvertiert Kontext in auditierbares Dictionary"""
        return {
            "actor": self.actor,
            "role": self.role,
            "auth_type": self.auth_type,
            "timestamp": self.timestamp.isoformat(),
            "reason": self.reason,
            "metadata": self.metadata
        }

class StatusStateMachine:
    """
    Zentrale Entscheidungsinstanz für Status-Transitions.
    Erzwingt deterministische, auditierbare Zustandsübergänge.
    
    Thread-safe für konkurrierende Transitions innerhalb derselben Instanz.
    """
    
    # Erlaubte Transitions: {from_status: {to_status, ...}}
    _ALLOWED_TRANSITIONS: Dict[SystemStatus, Set[SystemStatus]] = {
        SystemStatus.OK: {SystemStatus.NEEDS_REVIEW, SystemStatus.ERROR},
        SystemStatus.NEEDS_REVIEW: {SystemStatus.APPROVED, SystemStatus.REJECTED},
        SystemStatus.APPROVED: set(),
        SystemStatus.REJECTED: set(),
        SystemStatus.ERROR: set(),
    }
    
    # Admin-Override erlaubte Ziele
    _ADMIN_OVERRIDE_TARGETS = {SystemStatus.APPROVED, SystemStatus.REJECTED}
    
    def __init__(self, initial_status: SystemStatus = SystemStatus.OK):
        self._current_status = initial_status
        self._transition_history: List[Tuple[SystemStatus, SystemStatus, TransitionContext]] = []
        self._logger = logging.getLogger(__name__)
        self._lock = threading.RLock()  # Reentrant lock für Transitions
        
    @property
    def current_status(self) -> SystemStatus:
        """Thread-safe read access to current status"""
        with self._lock:
            return self._current_status
    
    def can_transition_to(self, target_status: SystemStatus) -> bool:
        """Prüft, ob Transition erlaubt ist (idempotent)"""
        with self._lock:
            return target_status in self._ALLOWED_TRANSITIONS.get(self._current_status, set())
    
    def transition(
        self,
        target_status: SystemStatus,
        context: TransitionContext,
        is_admin_override: bool = False
    ) -> SystemStatus:
        """
        Führt Status-Transition durch.
        
        Thread-safe: Nur eine Transition pro Instanz gleichzeitig.
        
        Args:
            target_status: Ziel-Status
            context: Audit-Kontext mit Actor-Info
            is_admin_override: True für expliziten Admin-Override
            
        Returns:
            Neuer Status
            
        Raises:
            StatusTransitionError: Bei illegaler Transition
            AdminOverrideError: Bei nicht autorisiertem Admin-Override
        """
        with self._lock:
            # Idempotenz: Wenn schon im Ziel-Status, keine Aktion
            if self._current_status == target_status:
                return self._current_status
            
            # Admin-Override Prüfung
            if is_admin_override:
                # 1. Prüfe erlaubte Ziel-Status
                if target_status not in self._ADMIN_OVERRIDE_TARGETS:
                    raise StatusTransitionError(
                        f"Admin-Override zu {target_status} nicht erlaubt. "
                        f"Erlaubt: {self._ADMIN_OVERRIDE_TARGETS}",
                        self._current_status,
                        target_status
                    )
                # 2. Prüfe Admin-Rolle
                if context.role != "admin":
                    raise AdminOverrideError(
                        f"Admin-Override nur mit Rolle 'admin' erlaubt. "
                        f"Aktuelle Rolle: {context.role}",
                        context.actor,
                        context.role
                    )
                self._logger.warning(
                    f"Admin-Override durch {context.actor}: "
                    f"{self._current_status} -> {target_status}"
                )
            else:
                # Normale Transition validieren
                if not self.can_transition_to(target_status):
                    raise StatusTransitionError(
                        f"Illegale Transition: {self._current_status} -> {target_status}. "
                        f"Erlaubte Übergänge: {self._ALLOWED_TRANSITIONS.get(self._current_status)}",
                        self._current_status,
                        target_status
                    )
            
            # Transition durchführen
            old_status = self._current_status
            self._current_status = target_status
            
            # Audit-Log
            self._transition_history.append((old_status, target_status, context))
            self._log_transition(old_status, target_status, context, is_admin_override)
            
            return self._current_status
    
    def _log_transition(
        self,
        old_status: SystemStatus,
        new_status: SystemStatus,
        context: TransitionContext,
        is_admin_override: bool
    ):
        """Structured logging für Audit-Trail"""
        self._logger.info(
            "Status transition",
            extra={
                "old_status": str(old_status),
                "new_status": str(new_status),
                "actor": context.actor,
                "role": context.role,
                "auth_type": context.auth_type,
                "timestamp": context.timestamp.isoformat(),
                "admin_override": is_admin_override,
                "reason": context.reason,
                "component": "StatusStateMachine",
                "metadata": json.dumps(context.metadata, default=str)
            }
        )
    
    def get_transition_history(self) -> Tuple[Tuple[SystemStatus, SystemStatus, TransitionContext], ...]:
        """Gibt vollständigen Audit-Trail zurück (Read-only, thread-safe)"""
        with self._lock:
            return tuple(self._transition_history)
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialisiert StateMachine für persistenten Storage"""
        with self._lock:
            return {
                "current_status": str(self._current_status),
                "transition_history": [
                    {
                        "from": str(from_status),
                        "to": str(to_status),
                        "context": context.to_audit_dict()
                    }
                    for from_status, to_status, context in self._transition_history
                ]
            }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "StatusStateMachine":
        """Deserialisiert StateMachine aus persistentem Storage"""
        machine = cls(SystemStatus(data["current_status"]))
        
        # Rekonstruiere Transition History
        for entry in data.get("transition_history", []):
            context_data = entry["context"]
            context = TransitionContext(
                actor=context_data["actor"],
                role=context_data["role"],
                auth_type=context_data["auth_type"],
                timestamp=datetime.fromisoformat(context_data["timestamp"]),
                reason=context_data["reason"],
                metadata=context_data["metadata"]
            )
            machine._transition_history.append((
                SystemStatus(entry["from"]),
                SystemStatus(entry["to"]),
                context
            ))
        
        return machine

# ==================== STORAGE INTERFACE ====================

class StateMachineStorage(ABC):
    """
    Abstract storage interface für persistente State-Machine-Verwaltung.
    
    Enterprise-Produktionssysteme benötigen persistente, skalierbare Storage-Lösungen
    (z.B. Datenbank, Redis, etc.) statt In-Memory-Dictionaries.
    """
    
    @abstractmethod
    def save(self, request_id: str, state_machine: StatusStateMachine) -> None:
        """Speichert State-Machine persistent"""
        pass
    
    @abstractmethod
    def load(self, request_id: str) -> Optional[StatusStateMachine]:
        """Lädt State-Machine aus persistentem Storage"""
        pass
    
    @abstractmethod
    def delete(self, request_id: str) -> None:
        """Entfernt State-Machine aus Storage"""
        pass
    
    @abstractmethod
    def exists(self, request_id: str) -> bool:
        """Prüft, ob Request existiert"""
        pass

class InMemoryStorage(StateMachineStorage):
    """
    In-Memory Implementation - NICHT für Produktion geeignet!
    
    Nur für Entwicklung/Testing. Enterprise-Umgebungen benötigen
    persistente, skalierbare Lösungen (Datenbank, Redis, etc.).
    """
    
    def __init__(self):
        self._storage: Dict[str, Dict[str, Any]] = {}  # Serialized storage
        self._lock = threading.RLock()
    
    def save(self, request_id: str, state_machine: StatusStateMachine) -> None:
        with self._lock:
            self._storage[request_id] = state_machine.to_dict()
    
    def load(self, request_id: str) -> Optional[StatusStateMachine]:
        with self._lock:
            if request_id not in self._storage:
                return None
            return StatusStateMachine.from_dict(self._storage[request_id])
    
    def delete(self, request_id: str) -> None:
        with self._lock:
            self._storage.pop(request_id, None)
    
    def exists(self, request_id: str) -> bool:
        with self._lock:
            return request_id in self._storage

# ==================== STATUS RESOLVER ====================

@dataclass
class ClassificationResult:
    """Input für Status-Resolver"""
    confidence: float
    hitl_required: bool
    approval: Optional[bool] = None
    admin_override: bool = False
    error_occurred: bool = False

class StatusResolver:
    """
    Single Source of Truth für initialen Status.
    Entscheidungstabelle als deterministische, pure Funktion.
    """
    
    @staticmethod
    def resolve_status(result: ClassificationResult) -> SystemStatus:
        """
        Bestimmt initialen Status basierend auf Business Rules.
        
        Deterministische Entscheidungstabelle:
        1. ERROR hat höchste Priorität
        2. Admin-Override überschreibt alle Regeln (nur mit expliziter Flag)
        3. HITL-Required + No Approval → NEEDS_REVIEW
        4. Sonst → OK
        
        Diese Funktion ist pure und hat keine Seiteneffekte.
        """
        # 1. Systemfehler (höchste Priorität)
        if result.error_occurred:
            return SystemStatus.ERROR
        
        # 2. Admin-Override (explizit erlaubt, erfordert separate Autorisierung)
        if result.admin_override and result.approval:
            return SystemStatus.APPROVED
        
        # 3. HITL-Regel (zentrale Business Rule laut Anforderung)
        if result.hitl_required and not result.approval:
            return SystemStatus.NEEDS_REVIEW
        
        # 4. Default: OK
        return SystemStatus.OK
    
    @staticmethod
    def create_initial_machine(result: ClassificationResult) -> StatusStateMachine:
        """
        Factory-Methode für initiale State Machine.
        
        Thread-safe: Jeder Aufruf erzeugt neue, isolierte Instanz.
        """
        initial_status = StatusResolver.resolve_status(result)
        return StatusStateMachine(initial_status)

# ==================== INTEGRATION HELPER ====================

class NovaPactStatusManager:
    """
    Integrations-Layer für bestehendes FastAPI-System.
    
    WICHTIG: Enterprise-Umgebungen benötigen persistenten Storage.
    Diese Klasse ist thread-safe für konkurrierende Requests.
    """
    
    def __init__(self, storage: Optional[StateMachineStorage] = None):
        """
        Initialisiert mit optionalem Storage.
        
        Standard: InMemoryStorage (NUR für Entwicklung).
        Produktion: Datenbank/Redis-basierte Implementation erforderlich.
        """
        self._storage = storage or InMemoryStorage()
        self._logger = logging.getLogger(__name__)
    
    def process_classification(
        self,
        request_id: str,
        classification_result: ClassificationResult,
        actor: str,
        role: str,
        auth_type: str
    ) -> SystemStatus:
        """
        Zentrale Verarbeitung für /run-Endpoint.
        
        Returns:
            Finaler Status für Response
            
        Thread-safe: Isolierte State-Machine pro Request.
        """
        # 1. Prüfe, ob Request bereits existiert (Idempotenz)
        if self._storage.exists(request_id):
            self._logger.warning(f"Request {request_id} bereits verarbeitet")
            existing = self._storage.load(request_id)
            return existing.current_status if existing else SystemStatus.ERROR
        
        # 2. Initialen Status deterministisch berechnen
        initial_status = StatusResolver.resolve_status(classification_result)
        
        # 3. State Machine erstellen (pro Request/Session)
        state_machine = StatusStateMachine(initial_status)
        
        # 4. Kontext für Audit-Log
        context = TransitionContext(
            actor=actor,
            role=role,
            auth_type=auth_type,
            timestamp=datetime.now(timezone.utc),
            reason="Initial classification",
            metadata={
                "confidence": classification_result.confidence,
                "hitl_required": classification_result.hitl_required,
                "admin_override": classification_result.admin_override
            }
        )
        
        # 5. State-Machine persistent speichern (Enterprise-Requirement)
        self._storage.save(request_id, state_machine)
        
        # 6. Audit-Logging
        self._logger.info(
            "Classification processed",
            extra={
                "request_id": request_id,
                "initial_status": str(initial_status),
                "actor": actor,
                "role": role,
                "confidence": classification_result.confidence,
                "hitl_required": classification_result.hitl_required,
                "component": "NovaPactStatusManager"
            }
        )
        
        return state_machine.current_status
    
    def manual_review_action(
        self,
        request_id: str,
        action: str,  # "approve" oder "reject"
        actor: str,
        role: str,
        auth_type: str,
        reason: Optional[str] = None
    ) -> SystemStatus:
        """
        Verarbeitet manuelle Review-Aktionen (HITL).
        
        Thread-safe: State-Machine wird geladen, modifiziert, gespeichert.
        
        Raises:
            KeyError: Wenn request_id nicht existiert
            StatusTransitionError: Bei illegaler Aktion
        """
        # 1. State-Machine laden
        state_machine = self._storage.load(request_id)
        if state_machine is None:
            raise KeyError(f"Request {request_id} nicht gefunden")
        
        # 2. Map Action zu Status
        action_map = {
            "approve": SystemStatus.APPROVED,
            "reject": SystemStatus.REJECTED
        }
        
        if action not in action_map:
            raise ValueError(f"Ungültige Aktion: {action}. Erlaubt: approve, reject")
        
        target_status = action_map[action]
        
        # 3. Transition durchführen
        context = TransitionContext(
            actor=actor,
            role=role,
            auth_type=auth_type,
            timestamp=datetime.now(timezone.utc),
            reason=reason or f"Manual {action}",
            metadata={"action": action}
        )
        
        try:
            new_status = state_machine.transition(target_status, context)
            self._storage.save(request_id, state_machine)  # Persistieren
            return new_status
        except StatusTransitionError as e:
            self._logger.error(
                f"Illegale Review-Aktion: {str(e)}",
                extra={
                    "request_id": request_id,
                    "actor": actor,
                    "action": action,
                    "current_status": str(state_machine.current_status)
                }
            )
            raise
    
    def admin_override(
        self,
        request_id: str,
        target_status: SystemStatus,
        actor: str,
        role: str,
        auth_type: str,
        reason: str
    ) -> SystemStatus:
        """
        Expliziter Admin-Override (nur für APPROVED/REJECTED).
        
        Erzwingt Rolle "admin" - Compliance-Requirement.
        """
        # 1. State-Machine laden
        state_machine = self._storage.load(request_id)
        if state_machine is None:
            raise KeyError(f"Request {request_id} nicht gefunden")
        
        # 2. Admin-Rolle prüfen (erste Ebene)
        if role != "admin":
            raise AdminOverrideError(
                f"Admin-Override erfordert Rolle 'admin'. Aktuell: {role}",
                actor,
                role
            )
        
        # 3. Transition durchführen (zweite Prüfung in state_machine.transition)
        context = TransitionContext(
            actor=actor,
            role=role,
            auth_type=auth_type,
            timestamp=datetime.now(timezone.utc),
            reason=f"Admin override: {reason}",
            metadata={"admin_override": True}
        )
        
        try:
            new_status = state_machine.transition(
                target_status,
                context,
                is_admin_override=True
            )
            self._storage.save(request_id, state_machine)
            return new_status
        except (StatusTransitionError, AdminOverrideError) as e:
            self._logger.error(
                f"Admin-Override fehlgeschlagen: {str(e)}",
                extra={
                    "request_id": request_id,
                    "actor": actor,
                    "role": role,
                    "target_status": str(target_status)
                }
            )
            raise
    
    def get_status(self, request_id: str) -> Optional[SystemStatus]:
        """Thread-safe Status-Abfrage"""
        state_machine = self._storage.load(request_id)
        return state_machine.current_status if state_machine else None
    
    def get_audit_trail(self, request_id: str) -> Optional[List[Dict[str, Any]]]:
        """Gibt vollständigen Audit-Trail für Compliance-Zwecke zurück"""
        state_machine = self._storage.load(request_id)
        if not state_machine:
            return None
        
        return [
            {
                "from": str(from_status),
                "to": str(to_status),
                "context": context.to_audit_dict()
            }
            for from_status, to_status, context in state_machine.get_transition_history()
        ]

# ==================== PRODUCTION STORAGE EXAMPLE ====================
"""
# Beispiel für Datenbank-Storage Implementation

import redis
from typing import Optional

class RedisStorage(StateMachineStorage):
    def __init__(self, redis_client: redis.Redis, ttl_seconds: int = 86400):
        self.redis = redis_client
        self.ttl = ttl_seconds  # Time-to-live in seconds (default: 24h)
    
    def save(self, request_id: str, state_machine: StatusStateMachine) -> None:
        serialized = json.dumps(state_machine.to_dict())
        self.redis.setex(f"status_machine:{request_id}", self.ttl, serialized)
    
    def load(self, request_id: str) -> Optional[StatusStateMachine]:
        data = self.redis.get(f"status_machine:{request_id}")
        if not data:
            return None
        return StatusStateMachine.from_dict(json.loads(data))
    
    def delete(self, request_id: str) -> None:
        self.redis.delete(f"status_machine:{request_id}")
    
    def exists(self, request_id: str) -> bool:
        return self.redis.exists(f"status_machine:{request_id}") > 0

# FastAPI Integration
from fastapi import FastAPI, Depends
from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    redis_client = redis.Redis(host="localhost", port=6379, db=0)
    storage = RedisStorage(redis_client, ttl_seconds=7*86400)  # 7 days
    app.state.status_manager = NovaPactStatusManager(storage)
    yield
    # Shutdown
    redis_client.close()

app = FastAPI(lifespan=lifespan)
"""
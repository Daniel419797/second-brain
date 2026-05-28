"""Short-term, semantic, and budgeted context memory for Friday."""

from __future__ import annotations

import datetime as dt
import hashlib
import importlib
import json
import re
import time
from collections import deque
from pathlib import Path
from typing import Any

from core import context_budget
from core.config import CHROMA_DIR, DATA_DIR, config_value, ensure_runtime_dirs

MAX_TURNS = int(config_value("memory_max_turns", 20))
REMEMBER_RE = re.compile(r"\[REMEMBER:\s*(.+?)\]", re.IGNORECASE)

_buffer: deque[dict[str, Any]] = deque(maxlen=MAX_TURNS)
_local_memory_file = DATA_DIR / "memory_store.json"
_archive_file = DATA_DIR / "logs" / "archived_memories.jsonl"

ensure_runtime_dirs()

_embedder = None
_client = None
_collection = None
_vector_import_failed = False


def add_user(text: str) -> None:
    _buffer.append({"role": "user", "content": text})


def add_assistant(text: str) -> None:
    _buffer.append({"role": "assistant", "content": text})
    _extract_and_store(text)


def add_tool_result(tool_use_id: str, result: str) -> None:
    _buffer.append(
        {
            "role": "user",
            "content": [{"type": "tool_result", "tool_use_id": tool_use_id, "content": result}],
        }
    )


def get_messages() -> list[dict[str, Any]]:
    return list(_buffer)


def add(text: str, user_id: str = "jarvis", metadata: dict[str, Any] | None = None) -> str:
    return _store_fact(text, user_id=user_id, metadata=metadata)


def search(query: str, user_id: str = "jarvis", n: int = 3) -> list[str]:
    return recall(query, n=n, user_id=user_id)


def recall(query: str, n: int = 3, user_id: str = "jarvis") -> list[str]:
    start = time.perf_counter()
    if not query:
        return []
    collection, embedder = _vector_store()
    if collection is not None and embedder is not None:
        try:
            embedding = embedder.encode(query).tolist()
            results = collection.query(query_embeddings=[embedding], n_results=n, where={"user_id": user_id})
            docs = results.get("documents") or []
            ids = (results.get("ids") or [[]])[0]
            metadatas = (results.get("metadatas") or [[]])[0]
            _reinforce_vector_memories(ids, metadatas)
            return list(docs[0]) if docs else []
        except Exception:
            pass
        finally:
            _log_latency(start)
    docs = _search_local(query, user_id=user_id, n=n)
    _log_latency(start)
    return docs


def remember_fact(fact: str, user_id: str = "jarvis", metadata: dict[str, Any] | None = None) -> None:
    add(fact, user_id=user_id, metadata=metadata)


def strip_remember_tags(text: str) -> str:
    return re.sub(r"\s*\[REMEMBER:\s*.+?\]\s*", " ", text or "", flags=re.IGNORECASE).strip()


def build_context(user_text: str, facts: list[str] | None = None, agent_id: str = "jarvis") -> str:
    semantic = facts if facts is not None else recall(user_text, n=int(config_value("memory_context_facts", 3)), user_id=agent_id)
    graph_lines = _graph_recall(user_text)
    episodic = _episodic_summary(agent_id)
    sections = [
        {
            "title": "Semantic Memory",
            "text": "\n".join(f"- {fact}" for fact in semantic),
            "budget": int(config_value("context_budget_semantic_tokens", 1500)),
        },
        {
            "title": "Associative Knowledge Graph",
            "text": "\n".join(f"- {line}" for line in graph_lines),
            "budget": int(config_value("context_budget_graph_tokens", 1500)),
        },
        {
            "title": "Recent Episodic Memory",
            "text": episodic,
            "budget": int(config_value("context_budget_episodic_tokens", 1000)),
        },
    ]
    if bool(config_value("context_include_conversation_section", False)):
        sections.append(
            {
                "title": "Conversation",
                "text": _conversation_text(),
                "budget": int(config_value("context_budget_conversation_tokens", 10000)),
            }
        )
    return context_budget.build_context_sections(
        sections,
        max_tokens=int(config_value("context_budget_max_tokens", 180000)),
        summarizer=None,
    )


def decay_activation_scores(rate: float | None = None, prune_threshold: float | None = None) -> dict[str, int]:
    decay = float(rate if rate is not None else config_value("memory_activation_decay_rate", 0.05))
    threshold = float(prune_threshold if prune_threshold is not None else config_value("memory_activation_prune_threshold", 0.1))
    entries = _load_local_entries()
    kept: list[dict[str, Any]] = []
    archived: list[dict[str, Any]] = []
    for entry in entries:
        score = float(entry.get("activation_score", 1.0))
        entry["activation_score"] = max(0.0, round(score * (1.0 - decay), 6))
        entry["updated_at"] = _now()
        if entry["activation_score"] < threshold:
            archived.append(entry)
        else:
            kept.append(entry)
    if archived:
        _archive_memories(archived)
    _save_local_entries(kept)
    return {"decayed": len(entries), "archived": len(archived)}


def all_memories(include_archived: bool = False) -> list[dict[str, Any]]:
    entries = _load_local_entries()
    if include_archived:
        entries.extend(_load_archived_entries())
    return entries


def clear_session() -> None:
    _buffer.clear()


def wipe_all() -> None:
    collection, _ = _vector_store()
    if collection is not None:
        try:
            existing = collection.get()
            ids = existing.get("ids", [])
            if ids:
                collection.delete(ids=ids)
        except Exception:
            pass
    for path in [_local_memory_file, _legacy_fallback_file(), _archive_file]:
        if path.exists():
            path.unlink()
    try:
        from core import adaptive_attention, agent_blackboard, agent_memory, agent_thought_bus, android_companion, app_state_memory, audit_log, autonomous_debugger, autonomous_learning, autonomous_qa_lab, backup_recovery, barge_in, browser_extension_bridge, codebase_standards, context_aware_silence, continuity_brain, capability_center, competence, contextual_workspace, daily_companion, deep_project_autopilot, emotion_tone, environment_awareness, episodic_store, error_radar, evaluation_lab, event_nervous_system, executive_capabilities, goal_regulation, knowledge_graph, learning_coach, local_file_intelligence, long_term_learning, meeting_study_companion, mission_control, model_router_brain, notification_center, offline_survival, operating_rhythm, pc_awareness, pc_timeline, personal_command_memory, personal_crm, personal_data_timeline, personal_finance, personal_knowledge_vault, personal_life_os, personal_safety_guardian, phone_bridge, phone_mesh, private_embedding_memory, privacy_vault, project_autopilot, project_watchdog, proactive_guardian, release_manager, research_briefings, sandbox_simulation, self_debugger, self_reflection, semantic_search, skill_evolution, skill_library, skill_training_studio, task_contracts, trust_proof, voice_reliability, world_model

        adaptive_attention.wipe_all()
        agent_blackboard.wipe_all()
        agent_memory.wipe_all()
        agent_thought_bus.wipe_all()
        android_companion.wipe_all()
        app_state_memory.wipe_all()
        audit_log.wipe_all()
        autonomous_debugger.wipe_all()
        autonomous_learning.wipe_all()
        autonomous_qa_lab.wipe_all()
        barge_in.wipe_all()
        backup_recovery.wipe_all()
        browser_extension_bridge.wipe_all()
        context_aware_silence.wipe_all()
        continuity_brain.wipe_all()
        capability_center.wipe_all()
        competence.wipe_all()
        contextual_workspace.wipe_all()
        daily_companion.wipe_all()
        deep_project_autopilot.wipe_all()
        emotion_tone.wipe_all()
        environment_awareness.wipe_all()
        episodic_store.wipe_all()
        error_radar.wipe_all()
        evaluation_lab.wipe_all()
        event_nervous_system.wipe_all()
        executive_capabilities.wipe_all()
        goal_regulation.wipe_all()
        knowledge_graph.wipe_all()
        learning_coach.wipe_all()
        local_file_intelligence.wipe_all()
        long_term_learning.wipe_all()
        meeting_study_companion.wipe_all()
        mission_control.wipe_all()
        model_router_brain.wipe_all()
        notification_center.wipe_all()
        offline_survival.wipe_all()
        operating_rhythm.wipe_all()
        pc_awareness.wipe_all()
        pc_timeline.wipe_all()
        personal_command_memory.wipe_all()
        personal_crm.wipe_all()
        personal_data_timeline.wipe_all()
        personal_finance.wipe_all()
        personal_knowledge_vault.wipe_all()
        personal_life_os.wipe_all()
        personal_safety_guardian.wipe_all()
        phone_bridge.wipe_all()
        phone_mesh.wipe_all()
        private_embedding_memory.wipe_all()
        privacy_vault.wipe_all()
        project_autopilot.wipe_all()
        project_watchdog.wipe_all()
        codebase_standards.wipe_all()
        proactive_guardian.wipe_all()
        release_manager.wipe_all()
        research_briefings.wipe_all()
        sandbox_simulation.wipe_all()
        self_debugger.wipe_all()
        self_reflection.wipe_all()
        semantic_search.wipe_all()
        skill_evolution.wipe_all()
        skill_library.wipe_all()
        skill_training_studio.wipe_all()
        task_contracts.wipe_all()
        trust_proof.wipe_all()
        voice_reliability.wipe_all()
        world_model.wipe_all()
    except Exception:
        pass
    clear_session()


def _extract_and_store(text: str) -> None:
    for fact in REMEMBER_RE.findall(text or ""):
        fact = fact.strip()
        if fact:
            _store_fact(fact)


def _store_fact(fact: str, user_id: str = "jarvis", metadata: dict[str, Any] | None = None) -> str:
    fact = " ".join(str(fact or "").strip().split())
    if not fact:
        return ""
    mem_id = "mem_" + hashlib.sha256(f"{user_id}:{fact}".encode("utf-8")).hexdigest()[:16]
    now = _now()
    memory_metadata = {
        "user_id": user_id,
        "created_at": now,
        "updated_at": now,
        "activation_score": 1.0,
        "retrieval_count": 0,
    }
    memory_metadata.update(_json_safe_dict(metadata or {}))
    collection, embedder = _vector_store()
    if collection is not None and embedder is not None:
        try:
            embedding = embedder.encode(fact).tolist()
            collection.upsert(documents=[fact], embeddings=[embedding], metadatas=[memory_metadata], ids=[mem_id])
        except Exception:
            pass
    _store_local_entry(mem_id, fact, user_id=user_id, metadata=memory_metadata)
    _learned_edge(user_id, fact)
    return mem_id


def _store_local_entry(mem_id: str, fact: str, user_id: str, metadata: dict[str, Any]) -> None:
    entries = _load_local_entries()
    for entry in entries:
        if entry.get("id") == mem_id:
            entry["text"] = fact
            entry["updated_at"] = _now()
            entry["activation_score"] = min(
                1.0,
                float(entry.get("activation_score", 1.0)) + float(config_value("memory_activation_reinforcement", 0.3)),
            )
            entry["metadata"] = {**entry.get("metadata", {}), **metadata}
            _save_local_entries(entries)
            return
    entries.append(
        {
            "id": mem_id,
            "text": fact,
            "user_id": user_id,
            "created_at": metadata.get("created_at", _now()),
            "updated_at": metadata.get("updated_at", _now()),
            "activation_score": float(metadata.get("activation_score", 1.0)),
            "retrieval_count": int(metadata.get("retrieval_count", 0)),
            "metadata": metadata,
        }
    )
    _save_local_entries(entries)


def _search_local(query: str, user_id: str, n: int) -> list[str]:
    entries = [entry for entry in _load_local_entries() if entry.get("user_id", "jarvis") == user_id]
    if not entries:
        return []
    terms = _terms(query)
    scored: list[tuple[float, int, dict[str, Any]]] = []
    for index, entry in enumerate(entries):
        text = str(entry.get("text") or "")
        text_terms = _terms(text)
        overlap = len(terms & text_terms)
        substring = 1 if query.lower() in text.lower() else 0
        activation = float(entry.get("activation_score", 1.0))
        score = overlap * 4 + substring * 5 + activation
        scored.append((score, index, entry))
    scored.sort(key=lambda item: (-item[0], -item[1]))
    selected = [entry for _score, _index, entry in scored[: max(1, n)]]
    _reinforce_local_memories([str(entry.get("id")) for entry in selected])
    return [str(entry.get("text") or "") for entry in selected if entry.get("text")]


def _reinforce_local_memories(ids: list[str]) -> None:
    if not ids:
        return
    reinforcement = float(config_value("memory_activation_reinforcement", 0.3))
    wanted = set(ids)
    entries = _load_local_entries()
    changed = False
    for entry in entries:
        if entry.get("id") in wanted:
            entry["activation_score"] = min(1.0, float(entry.get("activation_score", 1.0)) + reinforcement)
            entry["retrieval_count"] = int(entry.get("retrieval_count", 0)) + 1
            entry["updated_at"] = _now()
            changed = True
    if changed:
        _save_local_entries(entries)


def _reinforce_vector_memories(ids: list[str], metadatas: list[dict[str, Any]]) -> None:
    collection, _ = _vector_store()
    if collection is None or not ids:
        return
    reinforcement = float(config_value("memory_activation_reinforcement", 0.3))
    updated_metadatas = []
    for metadata in metadatas:
        item = dict(metadata or {})
        item["activation_score"] = min(1.0, float(item.get("activation_score", 1.0)) + reinforcement)
        item["retrieval_count"] = int(item.get("retrieval_count", 0)) + 1
        item["updated_at"] = _now()
        updated_metadatas.append(item)
    try:
        collection.update(ids=ids, metadatas=updated_metadatas)
    except Exception:
        return


def _load_local_entries() -> list[dict[str, Any]]:
    if _local_memory_file.exists():
        try:
            data = json.loads(_local_memory_file.read_text(encoding="utf-8"))
            if isinstance(data, list):
                return [_coerce_entry(item) for item in data if _coerce_entry(item)]
        except Exception:
            return []
    legacy = _legacy_fallback_file()
    if legacy.exists():
        try:
            data = json.loads(legacy.read_text(encoding="utf-8"))
            if isinstance(data, list):
                entries = [_coerce_entry(item) for item in data if _coerce_entry(item)]
                _save_local_entries(entries)
                return entries
        except Exception:
            return []
    return []


def _save_local_entries(entries: list[dict[str, Any]]) -> None:
    _local_memory_file.parent.mkdir(parents=True, exist_ok=True)
    _local_memory_file.write_text(json.dumps(entries, indent=2, ensure_ascii=True), encoding="utf-8")


def _coerce_entry(item: Any) -> dict[str, Any]:
    if isinstance(item, str):
        text = " ".join(item.strip().split())
        if not text:
            return {}
        mem_id = "mem_" + hashlib.sha256(f"jarvis:{text}".encode("utf-8")).hexdigest()[:16]
        return {
            "id": mem_id,
            "text": text,
            "user_id": "jarvis",
            "created_at": _now(),
            "updated_at": _now(),
            "activation_score": 1.0,
            "retrieval_count": 0,
            "metadata": {},
        }
    if isinstance(item, dict) and item.get("text"):
        entry = dict(item)
        entry.setdefault("id", "mem_" + hashlib.sha256(f"{entry.get('user_id', 'jarvis')}:{entry['text']}".encode("utf-8")).hexdigest()[:16])
        entry.setdefault("user_id", "jarvis")
        entry.setdefault("created_at", _now())
        entry.setdefault("updated_at", _now())
        entry.setdefault("activation_score", 1.0)
        entry.setdefault("retrieval_count", 0)
        entry.setdefault("metadata", {})
        return entry
    return {}


def _archive_memories(entries: list[dict[str, Any]]) -> None:
    _archive_file.parent.mkdir(parents=True, exist_ok=True)
    with _archive_file.open("a", encoding="utf-8") as fh:
        for entry in entries:
            fh.write(json.dumps(entry, ensure_ascii=True, default=str) + "\n")


def _load_archived_entries() -> list[dict[str, Any]]:
    if not _archive_file.exists():
        return []
    entries: list[dict[str, Any]] = []
    for line in _archive_file.read_text(encoding="utf-8").splitlines():
        try:
            item = json.loads(line)
        except Exception:
            continue
        if isinstance(item, dict):
            entries.append(item)
    return entries


def _vector_store() -> tuple[Any, Any]:
    global _client, _collection, _embedder, _vector_import_failed
    backend = str(config_value("memory_backend", "json")).lower()
    if backend not in {"chroma", "vector"}:
        return None, None
    if _collection is not None and _embedder is not None:
        return _collection, _embedder
    if _vector_import_failed:
        return None, None
    try:
        chromadb = importlib.import_module("chromadb")
        sentence_transformers = importlib.import_module("sentence_transformers")
        SentenceTransformer = sentence_transformers.SentenceTransformer
        _embedder = SentenceTransformer(str(config_value("memory_embedding_model", "all-MiniLM-L6-v2")))
        _client = chromadb.PersistentClient(path=str(CHROMA_DIR))
        _collection = _client.get_or_create_collection("jarvis_memory")
        return _collection, _embedder
    except Exception:
        _vector_import_failed = True
        _embedder = None
        _client = None
        _collection = None
        return None, None


def _conversation_text() -> str:
    lines: list[str] = []
    for message in _buffer:
        role = str(message.get("role", "user"))
        content = message.get("content", "")
        if isinstance(content, list):
            content = "[tool result]"
        lines.append(f"{role}: {content}")
    return "\n".join(lines)


def _graph_recall(user_text: str) -> list[str]:
    try:
        from core import knowledge_graph

        return knowledge_graph.spreading_recall(user_text, hops=int(config_value("memory_graph_hops", 2)), limit=8)
    except Exception:
        return []


def _episodic_summary(agent_id: str) -> str:
    try:
        from core import episodic_store

        return episodic_store.summarize_recent(agent_id=agent_id, limit=int(config_value("memory_context_events", 5)))
    except Exception:
        return ""


def _learned_edge(user_id: str, fact: str) -> None:
    try:
        from core import knowledge_graph

        knowledge_graph.add_edge(user_id.title(), "LEARNED", fact, source="memory")
    except Exception:
        return


def _json_safe_dict(values: dict[str, Any]) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for key, value in values.items():
        try:
            json.dumps(value)
            output[str(key)] = value
        except TypeError:
            output[str(key)] = str(value)
    return output


def _terms(text: str) -> set[str]:
    return {part for part in re.split(r"[^a-z0-9_+.-]+", str(text).lower()) if len(part) > 1}


def _legacy_fallback_file() -> Path:
    return CHROMA_DIR / "fallback_memory.json"


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).astimezone().isoformat(timespec="seconds")


def _log_latency(start: float) -> None:
    try:
        from output.display import log

        log("DEBUG", f"[MEM] recall latency={(time.perf_counter() - start) * 1000:.0f}ms")
    except Exception:
        return

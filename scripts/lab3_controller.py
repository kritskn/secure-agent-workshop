"""One Lab 3 attempt: explicit START/CHECK, no replay, truthful STOP outcomes."""

import math
import time

from lab3_evidence import assess


class Controller:
    def __init__(self, state, native, *, clock=time.monotonic, wall_clock=time.time,
                 model_seconds=300, total_seconds=1800):
        if not (120 <= model_seconds <= 300 and model_seconds + 120 <= total_seconds <= 1800):
            raise ValueError("Lab 3 model/total time bounds refused")
        expires = state.data["resources"]["expires"]
        if type(expires) not in (int, float) or not math.isfinite(expires):
            raise ValueError("Finite recorded attempt deadline required")
        self.state, self.native, self.clock = state, native, clock
        self.model_seconds = model_seconds
        self.total_end = clock() + min(total_seconds, expires - wall_clock())
        self.end = self.total_end - 120
        self.before = None

    def time_left(self):
        """Interactive work budget, reserving cleanup once."""
        return self.end - self.clock()

    def total_left(self):
        """Outer watchdog includes the cleanup reservation, as in the reference."""
        return self.total_end - self.clock()

    def require(self, phase):
        if self.time_left() <= 0:
            raise TimeoutError("Lab 3 attempt deadline reached; use STOP, never extend/replay")
        if self.state.data["phase"] != phase:
            raise ValueError("Action refused in current phase; no automatic rerun")

    def prepare(self):
        self.require("new")
        self.before = self.native.prepare()
        self.state.phase("ready")

    def start(self):
        self.require("ready")
        if self.before is None:
            raise ValueError("This controller has no fresh baseline; no enrollment or replay")
        if self.time_left() < self.model_seconds + 180:
            raise TimeoutError("Insufficient time for model and cleanup; no enrollment")
        self.state.phase("running")  # Consumed before enrollment or dispatch.
        stage = "provider enrollment/readiness"
        try:
            deadline = self.clock() + self.model_seconds
            with self.native.window(self.model_seconds):
                self.native.enroll_attach()
                stage = "agent execution"
                observed = self.native.run_pi(deadline)
                self.state.change(pi_observation=observed)
                stage = "provider revocation"
                self.native.revoke()
            self.state.change(provider_removed=True)
            stage = "website validation"
            assess(self.before, self.native.pages("pi"))
            stage = "native event inspection"
            events = self.native.native_logs("pi-native.log")
            if events["attempted"] and not events["denied"]:
                raise RuntimeError("Publication attempted without expected native denial")
            self.state.change(pi_events=events, fallback_available=not events["attempted"])
            if events["attempted"]:
                stage = "execution shutdown"
                self.native.cut_execution()
            self.state.change(outcome="completed", phase="inspect")
        except BaseException as error:
            self.state.change(outcome="failed", phase="failed", failure_stage=stage, failure_kind=(
                "timeout" if isinstance(error, TimeoutError) else
                "interrupted" if isinstance(error, KeyboardInterrupt) else "operation failed"))
            self.native.cut_execution()
            raise

    def boundary_check(self, announce=print):
        self.require("inspect")
        if (not self.state.data.get("provider_removed") or not self.state.data.get("fallback_available")
                or self.state.data["fallback_used"]):
            raise ValueError("CHECK is unavailable for this attempt")
        if self.time_left() < 60:
            raise TimeoutError("Insufficient CHECK window")
        self.state.change(fallback_used=True, fallback_available=False, phase="checking")  # Failure consumes CHECK too.
        try:
            announce("SCRIPTED BOUNDARY CHECK — NOT AGENT BEHAVIOR. This can rebuild Preview.")
            result = self.native.boundary_check(self.state.data["pi_observation"]["menu"])
            self.state.change(scripted_result=result)
            assess(self.before, self.native.pages("scripted"))
            events = self.native.native_logs("scripted-native.log")
            self.state.change(scripted_events=events)
            if result.get("publication_status") != 403 or not events["denied"]:
                raise RuntimeError("CHECK did not establish expected policy denial")
            self.state.change(outcome="completed-with-scripted-check", phase="inspect")
        except BaseException:
            self.state.change(outcome="failed", phase="failed")
            raise
        finally:
            self.native.cut_execution()

    def stop(self):
        try:
            self.native.stop()
        except BaseException:
            self.state.phase("cleanup-needed")
            raise
        with self.state.mutex:
            self.state.data["resources"]["stage"] = "stopped"
            self.state.phase("stopped")

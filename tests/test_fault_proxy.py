import unittest
from copy import deepcopy

from aftermath_bench.core import (
    CommitOutcome,
    FaultPlan,
    ToolEnvironment,
    TransitionFaultProxy,
)


class CounterEnv(ToolEnvironment):
    def __init__(self) -> None:
        self.state = {"primary": 0, "secondary": 0, "jobs": []}

    def list_tools(self) -> tuple[str, ...]:
        return ("increment_both",)

    def invoke(self, tool: str, **kwargs):
        if tool != "increment_both":
            raise KeyError(tool)
        self.state["primary"] += 1
        self.state["secondary"] += 1
        return {"ok": True}

    def snapshot(self):
        return deepcopy(self.state)


class FaultProxyTest(unittest.TestCase):
    def test_no_commit_and_full_commit_share_visible_error(self) -> None:
        no_commit_env = CounterEnv()
        no_commit = TransitionFaultProxy(
            no_commit_env,
            FaultPlan("increment_both", CommitOutcome.NO_COMMIT),
        )
        committed_env = CounterEnv()
        committed = TransitionFaultProxy(
            committed_env,
            FaultPlan(
                "increment_both",
                CommitOutcome.FULL_COMMIT_RESPONSE_LOST,
            ),
        )

        self.assertEqual(
            no_commit.invoke("increment_both"),
            committed.invoke("increment_both"),
        )
        self.assertEqual(no_commit_env.state["primary"], 0)
        self.assertEqual(committed_env.state["primary"], 1)

    def test_partial_commit_uses_explicit_state_transition(self) -> None:
        env = CounterEnv()

        def partial(_tool, _arguments):
            env.state["primary"] += 1

        proxy = TransitionFaultProxy(
            env,
            FaultPlan("increment_both", CommitOutcome.PARTIAL_COMMIT),
            partial_commit=partial,
        )
        result = proxy.invoke("increment_both")
        self.assertFalse(result["ok"])
        self.assertEqual(env.state, {"primary": 1, "secondary": 0, "jobs": []})

    def test_async_commit_creates_a_real_job(self) -> None:
        env = CounterEnv()

        def enqueue(tool, arguments):
            env.state["jobs"].append({"tool": tool, "arguments": arguments})

        proxy = TransitionFaultProxy(
            env,
            FaultPlan("increment_both", CommitOutcome.ASYNC_COMMIT_PENDING),
            enqueue_async=enqueue,
        )
        proxy.invoke("increment_both", amount=1)
        self.assertEqual(len(env.state["jobs"]), 1)
        self.assertEqual(
            proxy.events[0].injected_fault,
            CommitOutcome.ASYNC_COMMIT_PENDING.value,
        )


if __name__ == "__main__":
    unittest.main()


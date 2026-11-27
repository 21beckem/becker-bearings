import unittest

from interface.audio_queue import AudioQueue
from interface.contracts import SpeechMessageType, SpeechRequest


class AudioQueueTests(unittest.TestCase):
    def request(self, text, message_type, **kwargs):
        return SpeechRequest(
            text=text,
            message_id=kwargs.pop("message_id", text),
            message_type=message_type,
            **kwargs,
        )

    def test_menu_option_interrupts_and_requeues_instruction(self):
        queue = AudioQueue()
        queue.submit(self.request("Instructions", SpeechMessageType.INSTRUCTION))
        instruction = queue.begin_next()

        decision = queue.submit(
            self.request("New option", SpeechMessageType.MENU_OPTION)
        )

        self.assertTrue(decision.interrupt_current)
        queue.finish(instruction)
        option = queue.begin_next()
        self.assertEqual(option.text, "New option")
        queue.finish(option)
        self.assertEqual(queue.begin_next().text, "Instructions")

    def test_menu_entry_can_play_instructions_before_initial_option(self):
        queue = AudioQueue()
        queue.submit(self.request("Instructions", SpeechMessageType.INSTRUCTION))
        queue.submit(self.request(
            "Initial option", SpeechMessageType.MENU_OPTION,
            play_after_instructions=True,
        ))
        self.assertEqual(queue.begin_next().text, "Instructions")

    def test_menu_option_replaces_queued_options(self):
        queue = AudioQueue()
        queue.submit(self.request("old", SpeechMessageType.MENU_OPTION))
        queue.submit(self.request("new", SpeechMessageType.MENU_OPTION))
        self.assertEqual([item.text for item in queue.queued], ["new"])

    def test_instruction_replaces_older_queued_instruction(self):
        queue = AudioQueue()
        queue.submit(self.request("old", SpeechMessageType.INSTRUCTION))
        queue.submit(self.request("new", SpeechMessageType.INSTRUCTION))
        self.assertEqual([item.text for item in queue.queued], ["new"])

    def test_lens_entry_clears_non_errors_but_keeps_errors(self):
        queue = AudioQueue()
        queue.submit(self.request("option", SpeechMessageType.MENU_OPTION))
        queue.submit(self.request("error", SpeechMessageType.ERROR,
                                  error_key="camera"))
        queue.submit(self.request("entry", SpeechMessageType.LENS_ENTRY))
        self.assertEqual(
            [item.text for item in queue.queued], ["entry", "error"]
        )

    def test_errors_are_deduplicated_for_the_session(self):
        queue = AudioQueue()
        queue.submit(self.request("first", SpeechMessageType.ERROR,
                                  error_key="same"))
        queue.submit(self.request("repeat", SpeechMessageType.ERROR,
                                  error_key="same"))
        queue.submit(self.request("different", SpeechMessageType.ERROR,
                                  error_key="different"))
        self.assertEqual(
            [item.text for item in queue.queued], ["first", "different"]
        )


if __name__ == "__main__":
    unittest.main()

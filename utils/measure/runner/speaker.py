from .runner import MeasurementRunner, RunnerResult
from measure_util import MeasureUtil
from typing import Any
import inquirer

DURATION_PER_VOLUME_LEVEL = 20


class SpeakerRunner(MeasurementRunner):
    def __init__(self):
        self.measure_util: MeasureUtil = MeasureUtil()
        pass

    def run(self, answers: dict[str, Any], export_directory: str) -> RunnerResult | None:
        summary = {}

        duration = DURATION_PER_VOLUME_LEVEL
        if inquirer.confirm(
                'Ready to measure the standby-power? (Make sure your devices is in off or idle state in HA)',
                default=True):
            summary['standby'] = self.measure_util.take_average_measurement(duration)
        else:
            exit(0)
        print(
            f'Prepare to start measuring the power for {duration} seconds on each volume level starting with 10 until 100 (with steps of 10 between)')
        print('Recommend to stream Pink Sound from https://www.genelec.com/audio-test-signals')

        for volume in range(10, 101, 10):
            if inquirer.confirm(f'Set volume to {volume}% and confirm to start next {duration} second measurement',
                                default=True):
                summary[volume] = self.measure_util.take_average_measurement(duration)
        print('Summary of all average measurements:')
        for key in summary:
            print(key, ' : ', summary[key])

        return RunnerResult(model_json_data={})

    def get_questions(self) -> list[dict]:
        return []

    def measure_standby_power(self) -> float:
        #todo implement
        return 0

    def get_export_directory(self) -> str:
        return "speaker"

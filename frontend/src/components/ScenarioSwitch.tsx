import type { ReclamationScenario } from '../types'

interface ScenarioSwitchProps {
  scenario: ReclamationScenario
  onChange: (scenario: ReclamationScenario) => void
}

export default function ScenarioSwitch({ scenario, onChange }: ScenarioSwitchProps) {
  return (
    <div className="reclamation-scenario-switch" role="group" aria-label="复耕情景">
      <button
        type="button"
        aria-pressed={scenario === 'current'}
        onClick={() => onChange('current')}
      >
        当前情景
      </button>
      <button
        type="button"
        aria-pressed={scenario === 'future'}
        onClick={() => onChange('future')}
      >
        未来情景
      </button>
    </div>
  )
}

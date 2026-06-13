import sys; sys.path.insert(0, 'agent')
from src.swarm.presets import inspect_preset
result = inspect_preset('alpha_forge')
print('Valid:', result['valid'])
print('Errors:', result['errors'])
print('Warnings:', result['warnings'])
print()
print('Agents:', len(result['agents']))
for a in result['agents']:
    print(f"  {a['id']}: tools={a['tools']}")
print()
print('Tasks:', len(result['tasks']))
print('Layers:', len(result['layers']))
for i, layer in enumerate(result['layers']):
    print(f'  Layer {i}:')
    for t in layer:
        print(f'    - {t["task_id"]} ({t["agent_id"]})')

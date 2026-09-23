const select = document.querySelector('#scenario');
const button = document.querySelector('#submit');
const status = document.querySelector('#status');
const result = document.querySelector('#result');
let samples = [];
let busy = false;

function showStatus(message, error = false) {
  status.textContent = message;
  status.classList.toggle('error', error);
}

function errorMessage(response, data) {
  const detail = data?.detail;
  if (detail?.code === 'demo_busy' || detail?.code === 'demo_disabled' || detail?.code === 'demo_budget_exhausted') return detail.message;
  if (response.status === 422) return 'This scenario could not be accepted. Refresh the page to load the available presets.';
  if (response.status === 502) return 'Gemini could not classify this request. No request was saved. Please try again later.';
  if (response.status === 503) return 'The demo could not complete processing. A save may be unconfirmed; no automatic retry will be made.';
  return 'The request could not be completed. Please try again later.';
}

select.addEventListener('change', () => {
  document.querySelector('#preview').textContent = samples.find(s => s.sample_id === select.value)?.message || '';
});

document.querySelector('#demo-form').addEventListener('submit', async event => {
  event.preventDefault();
  if (busy || !select.value) return;
  busy = true;
  button.disabled = true;
  select.disabled = true;
  result.hidden = true;
  showStatus('Classifying and saving… Gemini may retry temporary failures, so this can take a little time.');
  try {
    const response = await fetch('/demo', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({sample_id: select.value})
    });
    const data = await response.json();
    if (!response.ok) {
      showStatus(errorMessage(response, data), true);
      return;
    }
    for (const [id, value] of Object.entries({
      'request-id': `Request #${data.id}`, category: data.category, priority: `${data.priority} priority`,
      summary: data.summary, action: data.suggested_action
    })) document.getElementById(id).textContent = String(value);
    document.getElementById('priority').dataset.priority = ['low', 'medium', 'high'].includes(data.priority) ? data.priority : '';
    result.hidden = false;
    showStatus('Classification saved successfully.');
  } catch {
    showStatus('The connection was interrupted or the response could not be read. The outcome is unknown; no automatic retry was made.', true);
  } finally {
    busy = false;
    button.disabled = false;
    select.disabled = false;
  }
});

async function loadSamples() {
  try {
    const response = await fetch('/demo/samples');
    const data = await response.json();
    if (!response.ok) {
      select.replaceChildren(new Option('Demo unavailable', ''));
      showStatus(errorMessage(response, data), true);
      return;
    }
    samples = data;
    select.replaceChildren();
    for (const sample of samples) {
      const option = document.createElement('option');
      option.value = sample.sample_id;
      option.textContent = sample.title;
      select.append(option);
    }
    select.disabled = false;
    button.disabled = false;
    select.dispatchEvent(new Event('change'));
    showStatus('Ready. Each submission uses one shared demo slot.');
  } catch {
    select.replaceChildren(new Option('Demo unavailable', ''));
    showStatus('Unable to load the demo. Please refresh later.', true);
  }
}
loadSamples();

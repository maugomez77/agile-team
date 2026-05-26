const { chromium } = require('playwright');

const API_URL = process.env.API_URL || 'https://sports-6viiq1lfd-mauriciogomez77-8197s-projects.vercel.app';
const UI_URL = process.env.UI_URL || 'https://sports-dashboard-kbblgi4tg-mauriciogomez77-8197s-projects.vercel.app';

let passed = 0, failed = 0;
const results = [];

function check(name, condition, detail = '') {
  if (condition) { passed++; results.push(`✓ ${name}`); }
  else { failed++; results.push(`✗ ${name}${detail ? ': ' + detail : ''}`); }
}

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage();

  // Capture console errors
  const errors = [];
  page.on('console', msg => { if (msg.type() === 'error') errors.push(msg.text()); });

  // === API TESTS ===
  console.log('--- API Tests ---');
  
  // Test: API returns 200
  let apiResp = await page.request.get(`${API_URL}/v1/sports?limit=3`);
  check('API returns 200', apiResp.ok());
  
  // Test: Response has articles
  if (apiResp.ok()) {
    let data = await apiResp.json();
    check('Response has articles', data.data?.articles?.length > 0);
    check('Response has pagination', !!data.data?.pagination);
    check('Response has status=success', data.status === 'success');
  }
  
  // Test: League filter works
  apiResp = await page.request.get(`${API_URL}/v1/sports?league=NBA&limit=3`);
  if (apiResp.ok()) {
    let data = await apiResp.json();
    check('NBA filter returns articles', data.data?.articles?.length > 0);
  }
  
  // Test: Search works
  apiResp = await page.request.get(`${API_URL}/v1/sports?q=Game&limit=3`);
  if (apiResp.ok()) {
    let data = await apiResp.json();
    check('Search returns results', data.data?.articles?.length > 0);
  }

  // === UI TESTS ===
  console.log('--- UI Tests ---');
  await page.goto(UI_URL, { waitUntil: 'domcontentloaded', timeout: 10000 });
  
  check('Page has title', (await page.title()).length > 0);
  check('No console errors', errors.length === 0, `${errors.length} errors found`);

  // Wait for articles to load
  await page.waitForTimeout(3000);

  // Check article cards
  const cards = await page.$$('[class*=card], [class*=article], .card, article');
  check('Article cards rendered', cards.length > 0, `found ${cards.length}`);

  // Check buttons
  const buttons = await page.$$('button');
  check('Filter buttons exist', buttons.length > 0, `found ${buttons.length}`);

  // Test click on a filter button
  if (buttons.length > 0) {
    await buttons[0].click();
    await page.waitForTimeout(1000);
    check('Filter button clickable', true);
  }

  // Test click on first card
  const firstCard = await page.$('[class*=card]:first-child, [class*=article]:first-child');
  if (firstCard) {
    await firstCard.click();
    await page.waitForTimeout(500);
    check('Card clickable', true);
  }

  // Check CSS
  const bodyBg = await page.evaluate(() => getComputedStyle(document.body).backgroundColor);
  check('CSS applied (background color)', bodyBg !== 'rgba(0, 0, 0, 0)');

  // Check headings
  const h1 = await page.$('h1');
  check('Has heading', !!h1);

  await browser.close();

  // Summary
  console.log(`\n=== RESULTS: ${passed}/${passed + failed} passed ===`);
  results.forEach(r => console.log(r));
  process.exit(failed > 0 ? 1 : 0);
})();

import { expect, test } from '@playwright/test';
import { installApiMocks, loginViaUi } from './helpers';

test('login smoke flow renders cases page', async ({ page }) => {
  await installApiMocks(page, { authedInitially: false });
  await loginViaUi(page);

  await expect(page).toHaveURL('/');
  await expect(page.getByRole('heading', { name: 'Cases' })).toBeVisible();
  await expect(page.getByText('WKS-042 Investigation')).toBeVisible();
  await expect(page.getByText('1 source')).toBeVisible();
});

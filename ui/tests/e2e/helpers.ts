import { type Page, type TestInfo } from '@playwright/test';

export const shot = (page: Page, info: TestInfo, name: string) => page.screenshot({ path: info.outputPath(`${name}.png`) });

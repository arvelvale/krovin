// 宣传片入口（promo.html）：纸面手绘 + 真实面板录屏。录屏由 scripts/record.mjs 生成到 public/rec/。
import "lxgw-wenkai-webfont/lxgwwenkai-regular.css";
import "lxgw-wenkai-webfont/lxgwwenkai-bold.css";
import "lxgw-wenkai-webfont/lxgwwenkaimono-regular.css";
import "../styles.css";
import { locate } from "../engine/timeline";
import { startPlayer } from "../player";
import { ensure, loadClips } from "./clips";
import { promoScenes, uiScenes } from "./scenes";
import script from "./script.json";
import src from "./scenes.ts?raw";

const clipsReady = loadClips(["login", "overview", "standup", "fix", "delegate", "models"]).catch((e) => {
  console.error(e);
});

startPlayer({
  scenes: promoScenes,
  script,
  audioDir: "promo-audio",
  sources: [src],
  async prepare(m, t) {
    await clipsReady;
    const need: Promise<void>[] = [ensure("login", 1.2)];
    for (const dt of [0, 0.25, 0.5, 1]) { // 当前帧必须到，后面几帧顺手预取
      const { sc } = locate(m, t + dt);
      const ui = uiScenes.find((x) => x.id === sc.scene.id);
      if (ui) {
        const p = ensure(ui.clip, ui.clipTimeAt(sc));
        if (dt === 0) need.push(p);
      }
    }
    await Promise.all(need);
  },
});

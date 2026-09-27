// 讲解片入口（index.html）。播放器逻辑在 player.ts，宣传片（promo.html）共用。
import "lxgw-wenkai-webfont/lxgwwenkai-regular.css";
import "lxgw-wenkai-webfont/lxgwwenkai-bold.css";
import "lxgw-wenkai-webfont/lxgwwenkaimono-regular.css";
import "./styles.css";
import { startPlayer } from "./player";
import { part1 } from "./scenes/part1";
import { part2 } from "./scenes/part2";
import { part3 } from "./scenes/part3";
import script from "./script.json";
import src1 from "./scenes/part1.ts?raw";
import src2 from "./scenes/part2.ts?raw";
import src3 from "./scenes/part3.ts?raw";

startPlayer({ scenes: [...part1, ...part2, ...part3], script, audioDir: "audio", sources: [src1, src2, src3] });

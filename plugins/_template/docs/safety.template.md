# Safety — __LABEL__

- **Network.** __NETWORK__ Every endpoint is listed in `.claude-plugin/plugin.json`; the Second
  Brain Link engine itself stays zero-network.
- **Never:** create an account, type a credential, solve a CAPTCHA, send an email, post on a social
  network, buy or book. `level:` (supervised by default) decides how many approvals a run asks for;
  the first real action of any kind is always gated.
- **Honesty fields.** A price only with `quoted_at`; a time or event only with `seen_at` and its
  source; a rate only once its denominator reaches 20; no bought data.
- **Your data.** Everything personal comes from `__LAYER__/profile/` in your brain; nothing is
  shipped in the plugin, nothing leaves the machine except the public reads above.

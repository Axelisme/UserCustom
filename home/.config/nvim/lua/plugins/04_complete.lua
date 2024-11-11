return {
  {
    "saghen/blink.cmp",
    -- enabled = false,
    opts = {
      accept = { auto_brackets = { enabled = false } },
      keymap = {
        preset = "enter",
        ["<C-space>"] = { "fallback" },
        ["<C-x>"] = { "hide_documentation", "hide" },
        ["<Up>"] = { "fallback" },
        ["<Down>"] = { "fallback" },
      },
    },
  },
}

return {
  {
    "saghen/blink.cmp",
    -- enabled = false,
    opts = {
      keymap = {
        preset = "enter",
        ["<C-space>"] = { "fallback" },
        ["<C-x>"] = { "hide_documentation", "hide" },
        ["<Up>"] = { "fallback" },
        ["<Down>"] = { "fallback" },
      },
      windows = { ghost_text = false },
    },
  },
}

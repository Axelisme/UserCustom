return {
  {
    "saghen/blink.cmp",
    -- enabled = false,
    opts = {
      keymap = {
        preset = "enter",
        ["<C-space>"] = { "fallback" },
        ["<C-x>"] = { "show", "hide" },
        ["<Up>"] = { "fallback" },
        ["<Down>"] = { "fallback" },
      },
      windows = { ghost_text = false },
    },
  },
}

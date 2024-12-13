return {
  {
    "saghen/blink.cmp",
    -- enabled = false,
    optional = true,
    opts = {
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

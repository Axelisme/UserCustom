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
  {
    "hrsh7th/nvim-cmp",
    -- enabled = false,
    optional = true,
    opts = function(_, opts)
      local cmp = require("cmp")
      local move_down = function(fallback)
        if cmp.visible() then
          ---@diagnostic disable-next-line: invisible
          if cmp.core.view.custom_entries_view:is_direction_top_down() then
            cmp.select_next_item()
          else
            fallback()
          end
        end
      end
      local move_up = function(fallback)
        if cmp.visible() then
          ---@diagnostic disable-next-line: invisible
          if cmp.core.view.custom_entries_view:is_direction_top_down() then
            fallback()
          else
            cmp.select_prev_item()
          end
        end
      end

      opts = opts or {}
      opts = vim.tbl_deep_extend("force", opts, {
        view = {
          entries = { name = "custom", selection_order = "bottom_up" },
          mapping = {
            ["<C-n>"] = cmp.mapping(move_down, { "i", "s" }),
            ["<C-p>"] = cmp.mapping(move_up, { "i", "s" }),
            ["<C-y>"] = cmp.mapping.confirm({ behavior = cmp.ConfirmBehavior.Replace }),
            ["<C-e>"] = cmp.mapping.close(),
            ["<CR>"] = cmp.mapping.confirm({ behavior = cmp.ConfirmBehavior.Replace }),
            ["<C-Space>"] = false,
            ["<S-CR>"] = false,
            ["<C-CR>"] = false,
          },
        },
      })
    end,
  },
}

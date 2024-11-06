return {
  {
    "hrsh7th/nvim-cmp",
    -- enabled = false,
    optional = true,
    opts = function(_, opts)
      local cmp = require("cmp")
      opts.experimental = { ghost_text = false }
      opts.view = { entries = { name = "custom", selection_order = "bottom_up" } }

      local toggle_menu = function()
        if cmp.visible() then
          cmp.close()
        else
          cmp.complete()
        end
      end

      local accept_completion = function()
        if cmp.visible() then
          cmp.confirm({ behavior = cmp.ConfirmBehavior.Replace })
        else
          cmp.complete()
        end
      end

      local move_down = function(fallback)
        if cmp.visible() then
          ---@diagnostic disable-next-line: invisible
          if cmp.core.view.custom_entries_view:is_direction_top_down() then
            cmp.select_next_item()
          else
            cmp.select_prev_item()
          end
        else
          fallback()
        end
      end

      local move_up = function(fallback)
        if cmp.visible() then
          ---@diagnostic disable-next-line: invisible
          if cmp.core.view.custom_entries_view:is_direction_top_down() then
            cmp.select_prev_item()
          else
            cmp.select_next_item()
          end
        else
          fallback()
        end
      end

      opts.mapping = {
        -- set new keymap
        ["<C-n>"] = cmp.mapping(move_down, { "i", "s" }),
        ["<C-p>"] = cmp.mapping(move_up, { "i", "s" }),
        ["<C-y>"] = cmp.mapping(accept_completion, { "i", "s" }),
        ["<S-CR>"] = cmp.mapping(accept_completion, { "i", "s" }),
        ["<C-x>"] = cmp.mapping(toggle_menu, { "i", "s" }),
        ["<C-b>"] = cmp.mapping.scroll_docs(-4),
        ["<C-f>"] = cmp.mapping.scroll_docs(4),
      }
    end,
  },
  {
    "saghen/blink.cmp",
    optional = true,
    opts = {
      keymap = {
        preset = "default",
        ["<C-space>"] = { "fallback" },
        ["<C-x>"] = { "show", "hide" },
        ["<Tab>"] = { "fallback" },
        ["<S-Tab>"] = { "fallback" },
      },
      windows = { ghost_text = false },
      sources = {
        -- list of enabled providers
        completion = {
          enabled_providers = { "lsp", "path", "buffer" },
        },
      },
    },
  },
}

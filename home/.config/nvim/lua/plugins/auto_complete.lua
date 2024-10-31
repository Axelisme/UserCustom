local in_ssh = os.getenv("SSH_TTY") ~= nil

return {
  -- copilot
  {
    "zbirenbaum/copilot.lua",
    enabled = not in_ssh,
    -- event = { "BufReadPre", "BufNewFile" },
    event = "InsertEnter",
    cmd = "Copilot",
    build = ":Copilot auth",
    keys = {
      {
        "<Tab>",
        function()
          require("copilot.suggestion").accept()
        end,
        mode = { "i", "s" },
        desc = "Copilot Accept",
      },
    },
    opts = {
      suggestion = {
        enabled = true,
        auto_trigger = true,
        keymap = {
          accept = "<C-Up>",
          accept_word = "<C-Right>",
          accept_line = "<C-Down>",
          dismiss = "<C-Left>",
        },
      },
    },
  },

  -- copilot icon
  { "AndreM222/copilot-lualine", event = "VeryLazy", enabled = not in_ssh },
  {
    "nvim-lualine/lualine.nvim",
    optional = true,
    opts = function(_, opts)
      if not in_ssh then
        table.insert(opts.sections.lualine_x, 1, { "copilot", symbols = { show_colors = true } })
      end
    end,
  },

  -- completion
  {
    "hrsh7th/nvim-cmp",
    -- enabled = false,
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
        -- disable follow keymap
        ["<Down>"] = cmp.config.disable,
        ["<Up>"] = cmp.config.disable,
        ["<CR>"] = cmp.config.disable,
        ["<C-Space>"] = cmp.config.disable,
        -- set new keymap
        ["<C-n>"] = cmp.mapping(move_down, { "i", "s" }),
        ["<C-p>"] = cmp.mapping(move_up, { "i", "s" }),
        ["<C-y>"] = cmp.mapping(accept_completion, { "i", "s" }),
        ["<S-CR>"] = cmp.mapping(accept_completion, { "i", "s" }),
        ["<C-b>"] = cmp.mapping(toggle_menu, { "i", "s" }),
      }
    end,
    -- disable <Tab> and <S-Tab>
    keys = function()
      return {}
    end,
  },
}

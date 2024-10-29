local icons = LazyVim.config.icons

return {
  {
    "nvim-lualine/lualine.nvim",
    opts = {
      sections = {
        lualine_a = { "mode" },
        lualine_b = { "branch" },
        lualine_c = { LazyVim.lualine.pretty_path() },
        lualine_x = {
          {
            "diff",
            symbols = {
              added = icons.git.added,
              modified = icons.git.modified,
              removed = icons.git.removed,
            },
            source = function()
              local gitsigns = vim.b.gitsigns_status_dict
              if gitsigns then
                return {
                  added = gitsigns.added,
                  modified = gitsigns.changed,
                  removed = gitsigns.removed,
                }
              end
            end,
          },
        },
        lualine_y = { { "filetype", icon_only = true, separator = "", padding = { left = 1, right = 1 } } },
        lualine_z = {},
      },
    },
    -- opts = function(_, opts)
    --   local icons = LazyVim.config.icons
    --   opts.sections = {
    --     lualine_a = { "mode" },
    --     lualine_b = { "branch" },
    --     lualine_c = { LazyVim.lualine.pretty_path() },
    --     lualine_x = {
    --       {
    --         "diff",
    --         symbols = {
    --           added = icons.git.added,
    --           modified = icons.git.modified,
    --           removed = icons.git.removed,
    --         },
    --         source = function()
    --           local gitsigns = vim.b.gitsigns_status_dict
    --           if gitsigns then
    --             return {
    --               added = gitsigns.added,
    --               modified = gitsigns.changed,
    --               removed = gitsigns.removed,
    --             }
    --           end
    --         end,
    --       },
    --     },
    --     lualine_y = { { "filetype", icon_only = true, separator = "", padding = { left = 1, right = 1 } } },
    --     lualine_z = {},
    --   }
    -- end,
  },
}

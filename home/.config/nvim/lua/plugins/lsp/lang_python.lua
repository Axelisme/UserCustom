local function shorter_name(filename)
  return filename:gsub(os.getenv("HOME"), "~"):gsub("/bin/python", "")
end

local function get_venv(variable)
  local venv = os.getenv(variable)
  if venv ~= nil and string.find(venv, "/") then
    local orig_venv = venv
    for w in orig_venv:gmatch("([^/]+)") do
      venv = w
    end
    venv = string.format("%s", venv)
  end
  return venv
end

return {
  {
    -- let mamba env can be find by venv-selector.nvim
    "linux-cultist/venv-selector.nvim",
    branch = "regexp",
    ft = "python",
    dependencies = { "neovim/nvim-lspconfig" },
    opts = {
      settings = {
        search = {
          cwd = false,
          workspace = false,
          micromamba_envs = {
            command = "$FD 'bin/python$' $HOME/micromamba/envs --full-path --color never",
            on_telescope_result_callback = shorter_name,
            type = "anaconda",
          },
        },
        options = {
          debug = true,
          activate_venv_in_terminal = true,
          set_environment_variables = true,
        },
      },
    },
  },
  {
    "lualine.nvim",
    opts = {
      sections = {
        lualine_y = {
          {
            function()
              local venv = get_venv("CONDA_PREFIX") or "NO ENV"
              return " " .. venv
            end,
            cond = function()
              return vim.bo.filetype == "python"
            end,
          },
        },
      },
    },
  },
  {
    "neovim/nvim-lspconfig",
    opts = {
      inlay_hints = { enabled = false },
      servers = {
        basedpyright = {
          settings = {
            pyright = {
              -- Using Ruff's import organizer
              disableOrganizeImports = true,
            },
            basedpyright = {
              analysis = {
                -- Basic type checking
                typeCheckingMode = "basic",
              },
            },
          },
        },
      },
    },
  },
}

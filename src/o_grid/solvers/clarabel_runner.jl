using Clarabel
using JSON
using LinearAlgebra
using SparseArrays

function sparse_matrix(data, rows, columns)
    row_indices = Int[]
    column_indices = Int[]
    values = Float64[]
    for entry in data
        push!(row_indices, Int(entry[1]))
        push!(column_indices, Int(entry[2]))
        push!(values, Float64(entry[3]))
    end
    return sparse(row_indices, column_indices, values, rows, columns)
end

function cone_from_data(data)
    kind = String(data["type"])
    dimension = Int(data["dimension"])
    if kind == "zero"
        return Clarabel.ZeroConeT(dimension)
    elseif kind == "nonnegative"
        return Clarabel.NonnegativeConeT(dimension)
    elseif kind == "second_order"
        return Clarabel.SecondOrderConeT(dimension)
    elseif kind == "positive_semidefinite"
        return Clarabel.PSDTriangleConeT(dimension)
    else
        error("unsupported Clarabel cone type: $kind")
    end
end

function finite_or_nothing(value)
    return isfinite(value) ? value : nothing
end

function finite_vector(values)
    return [finite_or_nothing(value) for value in values]
end

try
    problem = JSON.parse(read(stdin, String))
    n = Int(problem["n"])
    m = Int(problem["m"])
    P = sparse_matrix(problem["P"], n, n)
    A = sparse_matrix(problem["A"], m, n)
    q = Float64.(problem["q"])
    b = Float64.(problem["b"])
    cones = Clarabel.SupportedCone[cone_from_data(data) for data in problem["cones"]]
    settings = Clarabel.Settings(verbose = false)
    solver = Clarabel.Solver(P, q, A, b, cones, settings)
    Clarabel.solve!(solver)
    solution = solver.solution
    result = Dict(
        "status" => string(solution.status),
        "x" => finite_vector(solution.x),
        "z" => finite_vector(solution.z),
        "s" => finite_vector(solution.s),
        "objective" => finite_or_nothing(solution.obj_val),
        "iterations" => solution.iterations,
        "solve_time" => finite_or_nothing(solution.solve_time),
    )
    print(JSON.json(result))
catch error
    print(JSON.json(Dict("error" => sprint(showerror, error))))
    exit(1)
end

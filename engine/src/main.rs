use zjm_engine::constants::{EXIT_ERROR, EXIT_OK};

fn main() {
    let args: Vec<String> = std::env::args().skip(1).collect();
    match zjm_engine::cli::run(&args) {
        Ok(out) => {
            if !out.is_empty() {
                println!("{out}");
            }
            std::process::exit(EXIT_OK);
        }
        Err(fail) => {
            eprintln!("zjm-engine: {}", fail.msg.lines().next().unwrap_or("error"));
            std::process::exit(if fail.code == 0 { EXIT_ERROR } else { fail.code });
        }
    }
}
